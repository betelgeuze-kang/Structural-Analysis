#!/usr/bin/env python3
"""Build the canonical paid-pilot product readiness snapshot."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    tomllib = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "product_readiness_snapshot.json"
SCHEMA_VERSION = "product-readiness-snapshot.v1"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"


def _load_runner_policy_checker():
    module_path = ROOT / "scripts" / "check_github_actions_runner_policy.py"
    spec = importlib.util.spec_from_file_location(
        "check_github_actions_runner_policy",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load check_github_actions_runner_policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_runner_policy


check_runner_policy = _load_runner_policy_checker()


@dataclass(frozen=True)
class SnapshotInputPaths:
    readme: Path = Path("README.md")
    current_state: Path = Path("docs/commercialization-gap-current-state.md")
    pm_report: Path = PRODUCTIZATION / "pm_release_gate_report.json"
    gap_closure_status: Path = PRODUCTIZATION / "gap_closure_status.json"
    fresh_full_validation: Path = PRODUCTIZATION / "fresh_full_validation_lane_status.json"
    g1_terminal_gate: Path = PRODUCTIZATION / "mgt_g1_direct_residual_terminal_gate_report.json"
    g1_full_load_hip_newton_lane: Path = PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
    customer_shadow: Path = Path("implementation/phase1/customer_shadow_evidence_status.json")
    workstation_delivery: Path = Path("implementation/phase1/workstation_delivery_readiness.json")
    independent_product: Path = Path("implementation/phase1/release/independent_product_readiness.json")
    blocker_action_register: Path = PRODUCTIZATION / "pm_release_blocker_action_register.json"
    github_actions_ci_streak: Path = PRODUCTIZATION / "github_actions_ci_streak_evidence.json"
    ux_new_user_observation: Path = PRODUCTIZATION / "ux_new_user_observation_report.json"
    license_status_closure: Path = PRODUCTIZATION / "license_status_closure_report.json"
    external_benchmark_submission_readiness: Path = (
        Path("implementation/phase1/release/external_benchmark_submission_readiness.json")
    )
    external_benchmark_submission_updates: Path = (
        PRODUCTIZATION / "external_benchmark_submission_updates.json"
    )
    self_hosted_runner_status: Path = PRODUCTIZATION / "github_actions_self_hosted_runner_status.json"
    package_json: Path = Path("package.json")
    pyproject_toml: Path = Path("pyproject.toml")
    github_workflows: Path = Path(".github/workflows")


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path, blockers: list[str]) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        blockers.append(f"missing_artifact:{path}")
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        blockers.append(f"invalid_json:{path}:{exc.__class__.__name__}")
        return {}
    if not isinstance(payload, dict):
        blockers.append(f"invalid_json_object:{path}")
        return {}
    return payload


def _read_text(repo_root: Path, path: Path, blockers: list[str]) -> str:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        blockers.append(f"missing_doc:{path}")
        return ""
    return resolved.read_text(encoding="utf-8", errors="replace")


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


def _git_rev_parse(repo_root: Path, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--verify", text],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _commit_matches(value: Any, current_commit: str) -> bool:
    text = str(value or "").strip()
    if not text or not current_commit:
        return False
    return current_commit.startswith(text) or text.startswith(current_commit)


def _git_diff_name_only(repo_root: Path, source_commit: str, current_commit: str) -> list[str]:
    if not source_commit or not current_commit:
        return []
    try:
        output = subprocess.check_output(
            ["git", "diff", "--name-only", f"{source_commit}..{current_commit}"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _git_status_short(repo_root: Path) -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "status", "--short", "--untracked-files=normal"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [line.rstrip() for line in output.splitlines() if line.strip()]


def _git_status_path(row: str) -> str:
    text = row[3:].strip() if len(row) > 3 else row.strip()
    if " -> " in text:
        return text.rsplit(" -> ", 1)[1].strip()
    return text


def _receipt_commit_allowed_paths(paths: SnapshotInputPaths) -> set[str]:
    allowed_fields = {
        "readme",
        "current_state",
        "pm_report",
        "gap_closure_status",
        "fresh_full_validation",
        "g1_terminal_gate",
        "g1_full_load_hip_newton_lane",
        "customer_shadow",
        "workstation_delivery",
        "independent_product",
        "blocker_action_register",
        "github_actions_ci_streak",
        "ux_new_user_observation",
        "license_status_closure",
        "external_benchmark_submission_readiness",
        "external_benchmark_submission_updates",
        "self_hosted_runner_status",
    }
    return {
        _path_key
        for field in allowed_fields
        if (_path_key := _path_key_for_receipt(getattr(paths, field)))
    } | {_path_key_for_receipt(DEFAULT_OUT)}


def _path_key_for_receipt(path: Path) -> str:
    return path.as_posix()


def _receipt_commit_allowed_path(path: str, allowed_paths: set[str]) -> bool:
    if path in allowed_paths:
        return True
    if path in {"README.md", "docs/commercialization-gap-current-state.md"}:
        return True
    if path.startswith("docs/ai/dispatch/") and path.endswith(".md"):
        return True
    if path.startswith("implementation/phase1/release_evidence/productization/"):
        return path.endswith((".json", ".md"))
    if path in {
        "implementation/phase1/customer_shadow_evidence_status.json",
        "implementation/phase1/workstation_delivery_readiness.json",
        "implementation/phase1/release/independent_product_readiness.json",
        "implementation/phase1/release/external_benchmark_submission_readiness.json",
    }:
        return True
    return False


def _source_state_freshness(
    *,
    repo_root: Path,
    source_commit: Any,
    current_commit: str,
    changed_paths_cache: dict[str, list[str]],
    allowed_receipt_paths: set[str],
) -> tuple[bool, str, list[str]]:
    if _commit_matches(source_commit, current_commit):
        return True, "exact", []
    source = _git_rev_parse(repo_root, str(source_commit or ""))
    current = _git_rev_parse(repo_root, current_commit)
    if not source or not current:
        return False, "unresolved_source_commit", []
    if source not in changed_paths_cache:
        changed_paths_cache[source] = _git_diff_name_only(repo_root, source, current)
    changed_paths = changed_paths_cache[source]
    non_receipt_paths = [
        path
        for path in changed_paths
        if not _receipt_commit_allowed_path(path, allowed_receipt_paths)
    ]
    if not non_receipt_paths:
        return True, "receipt_only_commit", changed_paths
    return False, "non_receipt_paths_changed", non_receipt_paths


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _contract_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass")
        or payload.get("pass")
        or str(payload.get("status", "")).lower() == "ready"
        or str(payload.get("reason_code", "")).upper() == "PASS"
    )


def _release_area_counts_from_pm(pm_report: dict[str, Any]) -> tuple[int, int]:
    rows = [row for row in _as_list(pm_report.get("release_area_matrix")) if isinstance(row, dict)]
    if rows:
        return sum(1 for row in rows if row.get("ok") is True), len(rows)
    summary_line = str(pm_report.get("summary_line", ""))
    match = re.search(r"release_areas_green=(\d+)/(\d+)", summary_line)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0


def _doc_release_area_count(text: str) -> tuple[int, int] | None:
    for line in text.splitlines():
        if "release_areas_green" in line:
            match = re.search(r"release_areas_green=(\d+)\s*/\s*(\d+)", line)
            if match:
                return int(match.group(1)), int(match.group(2))
            continue
        if "PM release areas" not in line:
            continue
        tail = line.split("PM release areas", 1)[1]
        match = re.search(r"(\d+)\s*/\s*(\d+)", tail)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def _doc_open_blocker_count(text: str) -> int | None:
    patterns = (
        r"action register has\s+`?(\d+)`?\s+open blocker",
        r"open blocker(?:s)?[^0-9`]{0,20}`?(\d+)`?",
        r"open blocker[^\n`]*총\s+`?(\d+)`?개",
    )
    for line in text.splitlines():
        lowered = line.lower()
        if "open blocker" not in lowered and "action register" not in lowered:
            continue
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))
    return None


def _metadata_rows(
    *,
    artifacts: dict[str, dict[str, Any]],
    repo_root: Path,
    current_commit: str,
    allowed_receipt_paths: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    changed_paths_cache: dict[str, list[str]] = {}
    for name, payload in artifacts.items():
        source_commit = payload.get("source_commit_sha")
        generated_at = payload.get("generated_at")
        source_state_fresh, source_state_kind, changed_paths = _source_state_freshness(
            repo_root=repo_root,
            source_commit=source_commit,
            current_commit=current_commit,
            changed_paths_cache=changed_paths_cache,
            allowed_receipt_paths=allowed_receipt_paths,
        )
        row = {
            "artifact": name,
            "generated_at": generated_at,
            "source_commit_sha": source_commit,
            "reused_evidence": payload.get("reused_evidence"),
            "source_commit_matches_head": bool(_commit_matches(source_commit, current_commit)),
            "source_state_fresh": source_state_fresh,
            "source_state_kind": source_state_kind,
            "changed_paths_since_source_commit": changed_paths,
            "metadata_complete": bool(generated_at and source_commit is not None and "reused_evidence" in payload),
        }
        rows.append(row)
    return rows


def _schema_version_blockers(artifacts: dict[str, dict[str, Any]]) -> list[str]:
    return [
        f"schema_invalid:missing_schema_version:{name}"
        for name, payload in artifacts.items()
        if not payload.get("schema_version")
    ]


def _collect_lane_blockers(payload: dict[str, Any]) -> list[str]:
    blockers = [str(item) for item in _as_list(payload.get("blockers"))]
    lanes = _as_dict(payload.get("lanes"))
    for lane_name, lane_payload in lanes.items():
        lane = _as_dict(lane_payload)
        blockers.extend(
            f"{lane_name}::{item}" for item in _as_list(lane.get("blockers"))
        )
    return blockers


def _external_benchmark_receipt_counts(
    *,
    readiness: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, int]:
    summary = _as_dict(readiness.get("summary"))
    update_rows = _as_dict(updates.get("updates"))
    queue_count = max(
        4,
        len(update_rows),
        _as_int(summary.get("submission_queue_count"), 0),
    )
    pending_count = _as_int(summary.get("submission_receipt_pending_count"), -1)
    attached_count = _as_int(summary.get("submission_receipt_attached_count"), -1)
    update_attached_count = 0
    for row in update_rows.values():
        update = _as_dict(row)
        receipt_text = str(
            update.get("receipt_url")
            or update.get("submission_receipt_url")
            or update.get("submission_receipt")
            or ""
        ).strip()
        receipt_status = str(
            update.get("receipt_status")
            or update.get("submission_receipt_status")
            or ""
        ).strip().lower()
        closure_status = str(update.get("closure_evidence_status") or "").strip().lower()
        if (
            receipt_text
            and receipt_text.lower() != "pending"
            and not receipt_status.startswith("pending")
            and closure_status not in {"", "pending"}
        ):
            update_attached_count += 1
    if attached_count < 0:
        attached_count = update_attached_count
    if pending_count < 0:
        pending_count = max(queue_count - attached_count, 0)
    return {
        "queue_count": queue_count,
        "attached_count": attached_count,
        "pending_count": pending_count,
        "update_attached_count": update_attached_count,
        "update_count": len(update_rows),
    }


def _g1_child_hip_residual_refresh_summary(
    lane_payload: dict[str, Any],
) -> dict[str, Any]:
    evidence = _as_dict(lane_payload.get("child_hip_residual_refresh_evidence"))
    components = _as_dict(evidence.get("components"))
    required_components = (
        "matrix_free_global_krylov",
        "current_tangent_residual_row_correction",
    )
    component_ready = {
        key: bool(_as_dict(components.get(key)).get("ready"))
        for key in required_components
    }
    blockers = [str(item) for item in _as_list(evidence.get("blockers"))]
    if not evidence:
        blockers.append("child_hip_residual_refresh_evidence_missing")
    for key, ready in component_ready.items():
        if not ready:
            blockers.append(f"{key}_child_hip_residual_refresh_not_ready")
    blockers = sorted(dict.fromkeys(blockers))
    ready = bool(evidence.get("ready") is True and not blockers)
    return {
        "ready": ready,
        "blockers": blockers,
        "components": components,
    }


def _pyproject_project_metadata(
    repo_root: Path,
    path: Path,
    blockers: list[str],
) -> dict[str, str]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        blockers.append(f"missing_doc:{path}")
        return {}

    if tomllib is not None:
        try:
            payload = tomllib.loads(resolved.read_text(encoding="utf-8"))
        except Exception as exc:
            blockers.append(f"invalid_toml:{path}:{exc.__class__.__name__}")
            return {}
        project = payload.get("project", {})
        if not isinstance(project, dict):
            return {}
        return {
            "name": str(project.get("name", "")),
            "version": str(project.get("version", "")),
        }

    pyproject = resolved.read_text(encoding="utf-8", errors="replace")
    project: dict[str, str] = {}
    in_project = False
    value_pattern = re.compile(r"^([A-Za-z0-9_-]+)\s*=\s*(['\"])(.*?)\2")
    for raw_line in pyproject.splitlines():
        line = raw_line.strip()
        if line == "[project]":
            in_project = True
            continue
        if line.startswith("[") and line.endswith("]") and line != "[project]":
            in_project = False
        if not in_project:
            continue
        match = value_pattern.match(line)
        if match:
            project[match.group(1)] = match.group(3)
    return project


def _product_identity(repo_root: Path, paths: SnapshotInputPaths, blockers: list[str]) -> dict[str, Any]:
    package = _load_json(repo_root, paths.package_json, blockers)
    pyproject = _pyproject_project_metadata(repo_root, paths.pyproject_toml, blockers)
    package_name = str(package.get("name", ""))
    package_version = str(package.get("version", ""))
    pyproject_name = str(pyproject.get("name", ""))
    pyproject_version = str(pyproject.get("version", ""))
    name_matches = bool(package_name and pyproject_name and package_name == pyproject_name)
    version_matches = bool(
        package_version and pyproject_version and package_version == pyproject_version
    )
    if not package_name or not pyproject_name:
        blockers.append("product_identity_name_missing:package_json_or_pyproject")
    elif not name_matches:
        blockers.append("product_identity_name_mismatch:package_json_vs_pyproject")
    if not package_version or not pyproject_version:
        blockers.append("product_identity_version_missing:package_json_or_pyproject")
    elif not version_matches:
        blockers.append("product_identity_version_mismatch:package_json_vs_pyproject")
    return {
        "package_json": {"name": package_name, "version": package_version},
        "pyproject": {"name": pyproject_name, "version": pyproject_version},
        "name_matches": name_matches,
        "version_matches": version_matches,
        "matches": bool(name_matches and version_matches),
    }


def build_snapshot(
    *,
    repo_root: Path = ROOT,
    paths: SnapshotInputPaths = SnapshotInputPaths(),
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    repo_root = repo_root.resolve()
    current_commit = source_commit_sha if source_commit_sha is not None else _git_head(repo_root)
    allowed_receipt_paths = _receipt_commit_allowed_paths(paths)
    worktree_status_rows = (
        []
        if source_commit_sha is not None
        else _git_status_short(repo_root)
    )
    worktree_dirty_paths = [_git_status_path(row) for row in worktree_status_rows]
    worktree_non_receipt_dirty_paths = [
        path
        for path in worktree_dirty_paths
        if not _receipt_commit_allowed_path(path, allowed_receipt_paths)
    ]
    worktree_dirty = bool(worktree_non_receipt_dirty_paths)
    if worktree_dirty:
        blockers.append("stale_or_inconsistent:worktree_dirty")

    readme = _read_text(repo_root, paths.readme, blockers)
    current_state = _read_text(repo_root, paths.current_state, blockers)
    pm_report = _load_json(repo_root, paths.pm_report, blockers)
    gap_closure = _load_json(repo_root, paths.gap_closure_status, blockers)
    fresh = _load_json(repo_root, paths.fresh_full_validation, blockers)
    g1 = _load_json(repo_root, paths.g1_terminal_gate, blockers)
    g1_full_load_lane = _load_json(repo_root, paths.g1_full_load_hip_newton_lane, blockers)
    customer = _load_json(repo_root, paths.customer_shadow, blockers)
    workstation = _load_json(repo_root, paths.workstation_delivery, blockers)
    independent = _load_json(repo_root, paths.independent_product, blockers)
    action_register = _load_json(repo_root, paths.blocker_action_register, blockers)
    ci_streak = _load_json(repo_root, paths.github_actions_ci_streak, blockers)
    ux_new_user = _load_json(repo_root, paths.ux_new_user_observation, blockers)
    license_status = _load_json(repo_root, paths.license_status_closure, blockers)
    external_benchmark_readiness = _load_json(
        repo_root,
        paths.external_benchmark_submission_readiness,
        blockers,
    )
    external_benchmark_updates = _load_json(
        repo_root,
        paths.external_benchmark_submission_updates,
        blockers,
    )
    self_hosted_runner_status = _load_json(repo_root, paths.self_hosted_runner_status, blockers)
    runner_policy = check_runner_policy(
        workflow_dir=_resolve(repo_root, paths.github_workflows)
    )

    release_area_green, release_area_total = _release_area_counts_from_pm(pm_report)
    readme_release_area = _doc_release_area_count(readme)
    current_state_release_area = _doc_release_area_count(current_state)
    release_area_sources = {
        "pm_release_gate_report": [release_area_green, release_area_total],
        "README.md": list(readme_release_area) if readme_release_area else None,
        "docs/commercialization-gap-current-state.md": (
            list(current_state_release_area) if current_state_release_area else None
        ),
    }
    release_area_values = {
        tuple(value)
        for value in (
            (release_area_green, release_area_total),
            readme_release_area,
            current_state_release_area,
        )
        if value is not None and value != (0, 0)
    }
    if len(release_area_values) > 1:
        blockers.append("stale_or_inconsistent:release_area_count_conflict")

    register_summary = _as_dict(action_register.get("summary"))
    register_open_count = _as_int(register_summary.get("open_blocker_count"), -1)
    readme_open = _doc_open_blocker_count(readme)
    current_state_open = _doc_open_blocker_count(current_state)
    blocker_count_sources = {
        "pm_release_blocker_action_register": register_open_count if register_open_count >= 0 else None,
        "README.md": readme_open,
        "docs/commercialization-gap-current-state.md": current_state_open,
    }
    blocker_values = {
        value
        for value in (register_open_count if register_open_count >= 0 else None, readme_open, current_state_open)
        if value is not None
    }
    if len(blocker_values) > 1:
        blockers.append("stale_or_inconsistent:open_blocker_count_conflict")

    metadata_artifacts = {
        "pm_release_gate_report": pm_report,
        "gap_closure_status": gap_closure,
        "fresh_full_validation_lane_status": fresh,
        "mgt_g1_direct_residual_terminal_gate_report": g1,
        "g1_full_load_hip_newton_lane_report": g1_full_load_lane,
        "customer_shadow_evidence_status": customer,
        "workstation_delivery_readiness": workstation,
        "independent_product_readiness": independent,
        "github_actions_ci_streak_evidence": ci_streak,
        "ux_new_user_observation_report": ux_new_user,
        "license_status_closure_report": license_status,
        "external_benchmark_submission_readiness": external_benchmark_readiness,
        "external_benchmark_submission_updates": external_benchmark_updates,
    }
    schema_artifacts = {
        **metadata_artifacts,
        "github_actions_runner_policy": runner_policy,
        "github_actions_self_hosted_runner_status": self_hosted_runner_status,
    }
    blockers.extend(_schema_version_blockers(schema_artifacts))
    metadata_rows = _metadata_rows(
        artifacts=metadata_artifacts,
        repo_root=repo_root,
        current_commit=current_commit,
        allowed_receipt_paths=allowed_receipt_paths,
    )
    for row in metadata_rows:
        if not row["metadata_complete"]:
            blockers.append(f"stale_or_inconsistent:metadata_incomplete:{row['artifact']}")
        elif not row["source_state_fresh"]:
            blockers.append(f"stale_or_inconsistent:source_commit_mismatch:{row['artifact']}")

    pm_release_ready = bool(
        pm_report.get("limited_commercial_release_ready")
        and pm_report.get("release_area_gate_ready")
        and pm_report.get("full_release_gate_ready")
    )
    pm_full_blockers = [str(item) for item in _as_list(pm_report.get("full_release_blockers"))]
    release_area_blockers = [str(item) for item in _as_list(pm_report.get("release_area_blockers"))]
    if not pm_release_ready:
        blockers.extend(f"pm_release::{item}" for item in (pm_full_blockers or release_area_blockers))
        if not (pm_full_blockers or release_area_blockers):
            blockers.append("pm_release:not_ready_without_explicit_blockers")

    fresh_summary = _as_dict(fresh.get("summary"))
    lane_count = _as_int(fresh_summary.get("lane_count"), 0)
    fresh_receipts = _as_int(fresh_summary.get("fresh_validation_receipt_pass_count"), 0)
    fresh_present = _as_int(fresh_summary.get("fresh_validation_receipt_present_count"), 0)
    fresh_rows = [row for row in _as_list(fresh.get("rows")) if isinstance(row, dict)]
    fresh_row_pass_count = sum(1 for row in fresh_rows if row.get("pass") is True)
    fresh_row_fresh_count = sum(
        1 for row in fresh_rows if row.get("fresh_validation_receipt_fresh") is True
    )
    fresh_row_contract_count = sum(
        1 for row in fresh_rows if row.get("fresh_validation_receipt_contract_pass") is True
    )
    fresh_rows_ready = bool(
        not fresh_rows
        or (
            len(fresh_rows) >= lane_count
            and fresh_row_pass_count >= lane_count
            and fresh_row_fresh_count >= lane_count
            and fresh_row_contract_count >= lane_count
        )
    )
    fresh_ready = bool(
        _contract_pass(fresh)
        and lane_count > 0
        and fresh_receipts >= lane_count
        and fresh_present >= lane_count
        and fresh_rows_ready
    )
    if not fresh_ready:
        blockers.extend(f"fresh_full_validation::{item}" for item in _as_list(fresh.get("blockers")))
        if fresh_rows and fresh_row_pass_count < lane_count:
            blockers.append("fresh_full_validation::row_pass_count_below_lane_count")
        if fresh_rows and fresh_row_fresh_count < lane_count:
            blockers.append("fresh_full_validation::row_fresh_receipt_count_below_lane_count")
        if fresh_rows and fresh_row_contract_count < lane_count:
            blockers.append("fresh_full_validation::row_contract_pass_count_below_lane_count")
        if not _as_list(fresh.get("blockers")):
            blockers.append("fresh_full_validation:not_ready")

    customer_summary = _as_dict(customer.get("summary"))
    completed_shadow_cases = _as_int(customer_summary.get("completed_shadow_case_count"), 0)
    min_shadow_cases = _as_int(customer_summary.get("min_completed_shadow_cases"), 3)
    customer_ready = bool(_contract_pass(customer) and completed_shadow_cases >= min_shadow_cases)
    if not customer_ready:
        blockers.extend(f"customer_shadow::{item}" for item in _as_list(customer.get("blockers")))
        if not _as_list(customer.get("blockers")):
            blockers.append("customer_shadow:not_ready")

    ci_summary = _as_dict(ci_streak.get("summary"))
    ci_pr_threshold_pass = bool(ci_summary.get("pr_threshold_pass"))
    ci_nightly_threshold_pass = bool(ci_summary.get("nightly_threshold_pass"))
    ci_streak_ready = bool(
        _contract_pass(ci_streak)
        and ci_pr_threshold_pass
        and ci_nightly_threshold_pass
    )
    if not ci_streak_ready:
        ci_blockers = _collect_lane_blockers(ci_streak)
        blockers.extend(f"ci_streak::{item}" for item in ci_blockers)
        if not ci_blockers:
            blockers.append("ci_streak:not_ready")

    ux_summary = _as_dict(ux_new_user.get("summary"))
    ux_completion = ux_summary.get("completion_minutes")
    ux_max_minutes = ux_summary.get("max_completion_minutes", 30.0)
    ux_human_ready = bool(
        _contract_pass(ux_new_user)
        and ux_completion is not None
        and _as_float(ux_completion, default=999999.0) <= _as_float(ux_max_minutes, default=30.0)
        and not _as_list(ux_new_user.get("blockers"))
    )
    if not ux_human_ready:
        ux_blockers = _as_list(ux_new_user.get("blockers"))
        blockers.extend(f"human_ux::{item}" for item in ux_blockers)
        if not ux_blockers:
            blockers.append("human_ux:not_ready")

    license_ready = bool(
        _contract_pass(license_status)
        and not _as_list(license_status.get("blockers"))
    )
    if not license_ready:
        license_blockers = _as_list(license_status.get("blockers"))
        blockers.extend(f"license::{item}" for item in license_blockers)
        if not license_blockers:
            blockers.append("license:not_ready")

    external_benchmark_receipts = _external_benchmark_receipt_counts(
        readiness=external_benchmark_readiness,
        updates=external_benchmark_updates,
    )
    external_benchmark_updates_fresh = external_benchmark_updates.get("reused_evidence") is False
    external_benchmark_ready = bool(
        _contract_pass(external_benchmark_readiness)
        and external_benchmark_updates_fresh
        and external_benchmark_receipts["queue_count"] >= 4
        and external_benchmark_receipts["attached_count"] >= external_benchmark_receipts["queue_count"]
        and external_benchmark_receipts["pending_count"] == 0
    )
    if not external_benchmark_ready:
        if not external_benchmark_updates_fresh:
            blockers.append("external_benchmark::submission_updates_reused_evidence_not_fresh")
        blockers.append(
            "external_benchmark::submission_receipts_pending="
            f"{max(external_benchmark_receipts['pending_count'], 0)}"
        )

    g1_claim_boundary = str(g1.get("claim_boundary", ""))
    if "full_g1_closure_ready" in g1:
        g1_full_mesh_ready = bool(g1.get("full_g1_closure_ready"))
    else:
        g1_full_mesh_ready = bool(
            _contract_pass(g1)
            and "does not close full-mesh" not in g1_claim_boundary.lower()
            and "full-load" in g1_claim_boundary.lower()
            and not _as_list(g1.get("blockers"))
        )
    if not g1_full_mesh_ready:
        blockers.append("g1_full_mesh_full_load_not_closed")
        blockers.extend(
            f"g1::{item}" for item in _as_list(g1.get("full_g1_closure_blockers"))
        )
    g1_lane_checkpoint = _as_dict(g1_full_load_lane.get("checkpoint"))
    g1_lane_observed_load = _as_float(g1_lane_checkpoint.get("load_scale"), default=-1.0)
    g1_lane_required_load = _as_float(g1_full_load_lane.get("required_load_scale"), default=1.0)
    g1_lane_load_tolerance = _as_float(g1_full_load_lane.get("full_load_tolerance"), default=1.0e-12)
    g1_lane_reused_ok = g1_full_load_lane.get("reused_evidence") is False
    g1_lane_full_load_input_pass = g1_full_load_lane.get("full_load_input_pass") is True
    g1_lane_load_scale_pass = bool(
        g1_lane_observed_load >= g1_lane_required_load - g1_lane_load_tolerance
    )
    g1_lane_child_hip_refresh = _g1_child_hip_residual_refresh_summary(
        g1_full_load_lane
    )
    g1_lane_child_hip_refresh_ready = bool(g1_lane_child_hip_refresh["ready"])
    g1_full_load_lane_ready = bool(
        _contract_pass(g1_full_load_lane)
        and str(g1_full_load_lane.get("status", "")).lower() == "ready"
        and g1_lane_reused_ok
        and g1_lane_full_load_input_pass
        and g1_lane_load_scale_pass
        and g1_lane_child_hip_refresh_ready
        and not _as_list(g1_full_load_lane.get("blockers"))
    )
    if not g1_full_load_lane_ready:
        lane_blockers = _as_list(g1_full_load_lane.get("blockers"))
        blockers.extend(f"g1_full_load_lane::{item}" for item in lane_blockers)
        blockers.extend(
            f"g1_full_load_lane::{item}"
            for item in _as_list(g1_lane_child_hip_refresh.get("blockers"))
        )
        if not g1_lane_reused_ok:
            blockers.append("g1_full_load_lane::reused_evidence_not_false")
        if not g1_lane_full_load_input_pass:
            blockers.append("g1_full_load_lane::full_load_input_not_pass")
        if not g1_lane_load_scale_pass:
            blockers.append("g1_full_load_lane::observed_load_scale_below_required_full_load")
        if not lane_blockers:
            blockers.append("g1_full_load_lane:not_ready")

    workstation_delivery_ready = bool(
        _contract_pass(workstation) and not _as_list(workstation.get("blockers"))
    )
    if not workstation_delivery_ready:
        blockers.extend(f"workstation_delivery::{item}" for item in _as_list(workstation.get("blockers")))
    independent_product_ready = bool(
        (independent.get("independent_commercial_product_ready") or _contract_pass(independent))
        and not _as_list(independent.get("blockers"))
    )
    if not independent_product_ready:
        blockers.extend(f"independent_product::{item}" for item in _as_list(independent.get("blockers")))
        if not _as_list(independent.get("blockers")):
            blockers.append("independent_product:not_ready")

    identity = _product_identity(repo_root, paths, blockers)
    runner_policy_ready = bool(runner_policy.get("contract_pass"))
    if not runner_policy_ready:
        blockers.extend(f"runner_policy::{item}" for item in _as_list(runner_policy.get("blockers")))
    self_hosted_runner_ready = bool(
        self_hosted_runner_status.get("contract_pass")
        and str(self_hosted_runner_status.get("status", "")).lower() == "ready"
    )
    if not self_hosted_runner_ready:
        runner_blockers = _as_list(self_hosted_runner_status.get("blockers"))
        blockers.extend(
            f"self_hosted_runner::{item}" for item in runner_blockers
        )
        if not runner_blockers:
            blockers.append("self_hosted_runner:not_ready")

    schema_valid = bool(
        current_commit
        and all(payload.get("schema_version") for payload in schema_artifacts.values())
    )
    if not schema_valid:
        blockers.append("schema_invalid:required_snapshot_inputs_missing")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if str(item)))
    stale_or_inconsistent = any(item.startswith("stale_or_inconsistent:") for item in blockers)
    evidence_fresh = bool(schema_valid and not stale_or_inconsistent)
    paid_pilot_ready = bool(
        schema_valid
        and evidence_fresh
        and pm_release_ready
        and workstation_delivery_ready
        and customer_ready
        and ci_streak_ready
        and ux_human_ready
        and license_ready
        and external_benchmark_ready
        and fresh_ready
        and g1_full_mesh_ready
        and g1_full_load_lane_ready
        and identity["matches"]
        and runner_policy_ready
        and self_hosted_runner_ready
    )
    ga_enterprise_ready = bool(paid_pilot_ready and independent_product_ready and pm_report.get("ga_enterprise_ready"))
    release_ready = bool(paid_pilot_ready and not blockers)
    status = "ready" if release_ready else ("stale_or_inconsistent" if stale_or_inconsistent else "blocked")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": current_commit,
        "engine_version": ENGINE_VERSION,
        "reused_evidence": False,
        "schema_valid": schema_valid,
        "evidence_fresh": evidence_fresh,
        "workstation_delivery_ready": workstation_delivery_ready,
        "paid_pilot_ready": paid_pilot_ready,
        "independent_product_ready": independent_product_ready,
        "ga_enterprise_ready": ga_enterprise_ready,
        "release_ready": release_ready,
        "status": status,
        "reason_code": "PASS" if release_ready else status.upper(),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "claim_boundary": {
            "paid_pilot": (
                "paid_pilot_ready requires a clean canonical snapshot, full PM release-area gate, "
                "tracked CI streaks, human new-user observation, product/legal license closure, EB "
                "receipts, customer shadow minimum, fresh validation receipts, and full-mesh/full-load "
                "G1 closure."
            ),
            "contract_pass_vs_release_ready": (
                "Upstream contract_pass fields are component contract results. They are not treated as "
                "release_ready when release-area, evidence freshness, customer, fresh-validation, or G1 "
                "blockers remain."
            ),
            "g1": g1_claim_boundary,
            "fresh_full_validation": str(fresh.get("claim_boundary", "")),
            "customer_shadow": str(customer.get("claim_boundary", "")),
        },
        "components": {
            "pm_release": {
                "contract_pass": bool(pm_report.get("contract_pass")),
                "limited_commercial_release_ready": bool(pm_report.get("limited_commercial_release_ready")),
                "release_area_gate_ready": bool(pm_report.get("release_area_gate_ready")),
                "full_release_gate_ready": bool(pm_report.get("full_release_gate_ready")),
                "paid_pilot_candidate": bool(pm_report.get("paid_pilot_candidate")),
                "release_area_green_count": release_area_green,
                "release_area_total_count": release_area_total,
                "release_area_blocker_count": len(release_area_blockers),
                "full_release_blocker_count": len(pm_full_blockers),
            },
            "fresh_full_validation": {
                "contract_pass": bool(fresh.get("contract_pass")),
                "lane_count": lane_count,
                "fresh_validation_receipt_present_count": fresh_present,
                "fresh_validation_receipt_pass_count": fresh_receipts,
                "row_count": len(fresh_rows),
                "row_pass_count": fresh_row_pass_count,
                "row_fresh_receipt_count": fresh_row_fresh_count,
                "row_contract_pass_count": fresh_row_contract_count,
                "ready": fresh_ready,
            },
            "customer_shadow": {
                "contract_pass": bool(customer.get("contract_pass")),
                "completed_shadow_case_count": completed_shadow_cases,
                "min_completed_shadow_cases": min_shadow_cases,
                "ready": customer_ready,
            },
            "github_actions_ci_streak": {
                "contract_pass": bool(ci_streak.get("contract_pass")),
                "pr_threshold_pass": ci_pr_threshold_pass,
                "nightly_threshold_pass": ci_nightly_threshold_pass,
                "pr_consecutive_pass_count": _as_int(
                    ci_summary.get("pr_consecutive_pass_count"), 0
                ),
                "nightly_consecutive_pass_count": _as_int(
                    ci_summary.get("nightly_consecutive_pass_count"), 0
                ),
                "ready": ci_streak_ready,
            },
            "human_ux_observation": {
                "contract_pass": bool(ux_new_user.get("contract_pass")),
                "completion_minutes": ux_completion,
                "max_completion_minutes": ux_max_minutes,
                "ready": ux_human_ready,
            },
            "license_status": {
                "contract_pass": bool(license_status.get("contract_pass")),
                "status": str(_as_dict(license_status.get("summary")).get("status", "")),
                "ready": license_ready,
            },
            "external_benchmark_receipts": {
                "contract_pass": bool(external_benchmark_readiness.get("contract_pass")),
                **external_benchmark_receipts,
                "updates_reused_evidence": external_benchmark_updates.get("reused_evidence"),
                "updates_fresh": external_benchmark_updates_fresh,
                "ready": external_benchmark_ready,
            },
            "g1": {
                "contract_pass": bool(g1.get("contract_pass")),
                "full_mesh_full_load_ready": g1_full_mesh_ready,
                "full_g1_closure_ready": bool(g1.get("full_g1_closure_ready")),
                "full_load_hip_newton_lane_ready": g1_full_load_lane_ready,
                "full_load_hip_newton_lane_status": str(
                    g1_full_load_lane.get("status", "")
                ),
                "full_load_hip_newton_lane_reused_evidence": g1_full_load_lane.get("reused_evidence"),
                "full_load_hip_newton_lane_full_load_input_pass": g1_lane_full_load_input_pass,
                "full_load_hip_newton_lane_observed_load_scale": g1_lane_observed_load,
                "full_load_hip_newton_lane_required_load_scale": g1_lane_required_load,
                "full_load_hip_newton_child_hip_residual_refresh_ready": (
                    g1_lane_child_hip_refresh_ready
                ),
                "full_load_hip_newton_child_hip_residual_refresh": (
                    g1_lane_child_hip_refresh
                ),
            },
            "product_identity": identity,
            "github_actions_runner_policy": {
                "contract_pass": runner_policy_ready,
                "workflow_count": _as_int(runner_policy.get("workflow_count"), 0),
                "runs_on_count": _as_int(runner_policy.get("runs_on_count"), 0),
                "ready": runner_policy_ready,
            },
            "github_actions_self_hosted_runner": {
                "contract_pass": bool(self_hosted_runner_status.get("contract_pass")),
                "status": str(self_hosted_runner_status.get("status", "")),
                "required_labels": _as_list(self_hosted_runner_status.get("required_labels")),
                "ready_runner_count": _as_int(
                    self_hosted_runner_status.get("ready_runner_count"), 0
                ),
                "ready": self_hosted_runner_ready,
            },
        },
        "state_consistency": {
            "release_area_counts": release_area_sources,
            "open_blocker_counts": blocker_count_sources,
            "metadata_rows": metadata_rows,
            "github_actions_runner_policy": runner_policy,
            "worktree": {
                "dirty": worktree_dirty,
                "status_rows": worktree_status_rows,
                "dirty_paths": worktree_dirty_paths,
                "non_receipt_dirty_paths": worktree_non_receipt_dirty_paths,
            },
        },
        "artifacts": {
            field: str(getattr(paths, field))
            for field in paths.__dataclass_fields__
        },
    }


def _strip_volatile_for_compare(payload: Any) -> Any:
    """Return ``payload`` with volatile ``generated_at`` fields removed recursively."""
    if isinstance(payload, dict):
        return {
            key: _strip_volatile_for_compare(value)
            for key, value in payload.items()
            if key != "generated_at"
        }
    if isinstance(payload, list):
        return [_strip_volatile_for_compare(item) for item in payload]
    return payload


def _differing_top_level_keys(
    existing: dict[str, Any],
    generated: dict[str, Any],
    prefix: str = "",
) -> list[str]:
    """Return a list of dotted paths whose values differ between two normalized snapshots."""
    if existing == generated:
        return []
    if not isinstance(existing, dict) or not isinstance(generated, dict):
        return [prefix] if prefix else ["<root>"]
    differences: list[str] = []
    for key in sorted(set(existing) | set(generated)):
        sub_prefix = f"{prefix}.{key}" if prefix else key
        if existing.get(key) != generated.get(key):
            if isinstance(existing.get(key), dict) and isinstance(generated.get(key), dict):
                differences.extend(
                    _differing_top_level_keys(existing[key], generated[key], sub_prefix)
                )
            else:
                differences.append(sub_prefix)
    return differences


def check_snapshot_consistency(
    *,
    repo_root: Path,
    out_path: Path,
    paths: SnapshotInputPaths = SnapshotInputPaths(),
    source_commit_sha: str | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Non-mutating check that the stored snapshot matches a freshly generated one.

    The volatile ``generated_at`` field is ignored. All other semantic fields
    (commit, status, evidence freshness, blockers, component flags) must match.

    Returns ``(ok, message, generated_payload)``. ``generated_payload`` is the
    freshly generated snapshot for diagnostics when ``ok`` is ``False``.
    """
    if not out_path.exists():
        return False, f"snapshot_missing:{out_path.as_posix()}", None
    try:
        existing = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"snapshot_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}", None
    if not isinstance(existing, dict):
        return False, f"snapshot_invalid_object:{out_path.as_posix()}", None

    generated = build_snapshot(
        repo_root=repo_root,
        paths=paths,
        source_commit_sha=source_commit_sha,
    )

    existing_normalized = _strip_volatile_for_compare(existing)
    generated_normalized = _strip_volatile_for_compare(generated)

    if existing_normalized == generated_normalized:
        return True, "snapshot_consistent", generated

    differences = _differing_top_level_keys(existing_normalized, generated_normalized)
    return (
        False,
        "snapshot_semantic_mismatch:" + ",".join(differences),
        generated,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Non-mutating: compare the existing --out file with a freshly generated "
            "snapshot (ignoring generated_at) and exit non-zero if the stored "
            "snapshot is missing, unreadable, or semantically different. When "
            "combined with --fail-blocked, the matched snapshot must also be "
            "release-ready."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = _resolve(ROOT, args.out)
    if args.check:
        ok, message, generated = check_snapshot_consistency(
            repo_root=ROOT,
            out_path=out,
        )
        if not ok:
            print(f"Product readiness snapshot check FAILED: {message}", file=sys.stderr)
            return 2
        if args.fail_blocked and generated is not None and not generated["release_ready"]:
            print(
                "Product readiness snapshot check FAILED: snapshot_consistent_but_not_release_ready",
                file=sys.stderr,
            )
            return 1
        print(f"Product readiness snapshot check: {message}")
        return 0
    payload = build_snapshot()
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    out.write_text(text, encoding="utf-8")
    print(text if args.json else f"Product readiness snapshot: {payload['status']}", end="" if args.json else "\n")
    return 1 if args.fail_blocked and not payload["release_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
