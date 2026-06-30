#!/usr/bin/env python3
"""Build the canonical paid-pilot product readiness snapshot."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
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
AGGREGATOR_REUSE_POLICY = "product_readiness_snapshot_aggregates_release_readiness_inputs"
PM_RELEASE_UX_DUPLICATE_WRAPPERS = {
    "ux::human_new_user_observation_missing_or_failed",
    "ux::human_new_user_30min_sample_evidence_missing",
}


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
    commercial_gap_ledger_status: Path = PRODUCTIZATION / "commercial_gap_ledger_status.json"
    gap_ledger_evidence_audit: Path = PRODUCTIZATION / "gap_ledger_evidence_audit.json"
    phase1_core_api_contract: Path = PRODUCTIZATION / "phase1_core_api_contract_summary.json"
    developer_preview_readiness: Path = PRODUCTIZATION / "developer_preview_readiness.json"
    developer_preview_rc_status: Path = PRODUCTIZATION / "developer_preview_rc_status.json"
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
    paid_pilot_scope_guard: Path = PRODUCTIZATION / "paid_pilot_scope_guard_report.json"
    external_benchmark_submission_readiness: Path = (
        Path("implementation/phase1/release/external_benchmark_submission_readiness.json")
    )
    external_benchmark_submission_updates: Path = (
        PRODUCTIZATION / "external_benchmark_submission_updates.json"
    )
    phase3_release_control_cleanup_plan: Path = PRODUCTIZATION / "phase3_release_control_cleanup_plan.json"
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


def _git_show_text(repo_root: Path, commit: str, path: str) -> str | None:
    if not commit or not path:
        return None
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit}:{path}"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None


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


def _path_key_for_repo_path(repo_root: Path, path: Path) -> str:
    if path.is_absolute():
        try:
            return path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_path(repo_root: Path, path: Path) -> str:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return "missing"
    if resolved.is_file():
        return f"sha256:{_sha256_file(resolved)}"
    if resolved.is_dir():
        digest = hashlib.sha256()
        for child in sorted(item for item in resolved.rglob("*") if item.is_file()):
            key = _path_key_for_repo_path(repo_root, child)
            digest.update(key.encode("utf-8"))
            digest.update(b"\0")
            digest.update(_sha256_file(child).encode("ascii"))
            digest.update(b"\0")
        return f"sha256-dir:{digest.hexdigest()}"
    return "unsupported"


def _snapshot_input_checksums(
    repo_root: Path,
    paths: SnapshotInputPaths,
) -> dict[str, str]:
    return {
        _path_key_for_repo_path(repo_root, path): _sha256_path(repo_root, path)
        for path in _snapshot_source_paths(paths)
    }


def _snapshot_source_paths(paths: SnapshotInputPaths) -> list[Path]:
    return [
        Path("scripts/build_product_readiness_snapshot.py"),
        *[getattr(paths, field) for field in paths.__dataclass_fields__],
    ]


def _snapshot_source_artifacts(repo_root: Path, paths: SnapshotInputPaths) -> list[str]:
    return [
        _path_key_for_repo_path(repo_root, path)
        for path in _snapshot_source_paths(paths)
    ]


def _receipt_commit_allowed_paths(
    paths: SnapshotInputPaths,
    *,
    repo_root: Path = ROOT,
    additional_paths: tuple[Path, ...] = (),
) -> set[str]:
    allowed_fields = {
        "readme",
        "current_state",
        "pm_report",
        "gap_closure_status",
        "commercial_gap_ledger_status",
        "gap_ledger_evidence_audit",
        "phase1_core_api_contract",
        "developer_preview_readiness",
        "developer_preview_rc_status",
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
        "paid_pilot_scope_guard",
        "external_benchmark_submission_readiness",
        "external_benchmark_submission_updates",
        "phase3_release_control_cleanup_plan",
        "self_hosted_runner_status",
    }
    return {
        _path_key
        for field in allowed_fields
        if (_path_key := _path_key_for_receipt(getattr(paths, field)))
    } | {
        _path_key_for_receipt(DEFAULT_OUT),
        *(_path_key_for_repo_path(repo_root, path) for path in additional_paths),
    }


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
    if path.startswith("implementation/phase1/release_evidence/surface/") and path.endswith(".json"):
        return True
    if path in {
        "implementation/phase1/customer_shadow_evidence_status.json",
        "implementation/phase1/support_bundle_manifest.json",
        "implementation/phase1/workstation_delivery_readiness.json",
        "implementation/phase1/release/independent_product_readiness.json",
        "implementation/phase1/release/external_benchmark_submission_readiness.json",
    }:
        return True
    return False


def _source_state_freshness(
    *,
    artifact_name: str,
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
    relevant_paths = [
        path
        for path in non_receipt_paths
        if _artifact_relevant_source_path(artifact_name, path)
    ]
    if not relevant_paths:
        return True, "non_artifact_source_paths_changed", non_receipt_paths
    semantic_relevant_paths = [
        path
        for path in relevant_paths
        if not _open_data_generated_timestamp_only_change(
            repo_root=repo_root,
            source_commit=source,
            current_commit=current,
            path=path,
        )
    ]
    if not semantic_relevant_paths:
        return True, "generated_open_data_timestamp_only_commit", relevant_paths
    return False, "non_receipt_paths_changed", semantic_relevant_paths


def _open_data_generated_timestamp_only_change(
    *,
    repo_root: Path,
    source_commit: str,
    current_commit: str,
    path: str,
) -> bool:
    if not path.startswith("implementation/phase1/open_data/") or not path.endswith(".json"):
        return False
    source_text = _git_show_text(repo_root, source_commit, path)
    current_text = _git_show_text(repo_root, current_commit, path)
    if source_text is None or current_text is None:
        return False
    try:
        source_payload = json.loads(source_text)
        current_payload = json.loads(current_text)
    except Exception:
        return False
    return _strip_open_data_volatile_fields(source_payload) == _strip_open_data_volatile_fields(
        current_payload
    )


def _strip_open_data_volatile_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_open_data_volatile_fields(item)
            for key, item in value.items()
            if key not in {"generated_at", "generated_at_utc"}
        }
    if isinstance(value, list):
        return [_strip_open_data_volatile_fields(item) for item in value]
    return value


def _artifact_relevant_source_path(artifact_name: str, path: str) -> bool:
    snapshot_only_paths = {
        "scripts/build_product_readiness_snapshot.py",
    }
    if path in snapshot_only_paths:
        return False
    artifact_specific_paths = {
        "commercial_gap_ledger_status": {
            "scripts/report_commercial_gap_ledger_status.py",
            "implementation/phase1/commercial_gap_ledger_status.py",
        },
        "customer_shadow_evidence_status": {
            "scripts/check_customer_shadow_evidence_status.py",
        },
        "developer_preview_rc_status": {
            "scripts/build_developer_preview_rc_status.py",
        },
        "developer_preview_readiness": {
            "scripts/build_developer_preview_readiness.py",
        },
        "external_benchmark_submission_readiness": {
            "implementation/phase1/generate_external_benchmark_submission_readiness.py",
        },
        "external_benchmark_submission_updates": {
            "scripts/build_p1_evidence_sidecar_updates.py",
        },
        "fresh_full_validation_lane_status": {
            "scripts/build_fresh_full_validation_lane_status.py",
        },
        "g1_full_load_hip_newton_lane_report": {
            "scripts/run_g1_full_load_hip_newton_lane.py",
        },
        "gap_closure_status": {
            "scripts/report_gap_closure_status.py",
        },
        "gap_ledger_evidence_audit": {
            "scripts/build_gap_ledger_evidence_audit.py",
        },
        "github_actions_ci_streak_evidence": {
            "scripts/build_github_actions_ci_streak_evidence.py",
        },
        "license_status_closure_report": {
            "scripts/build_license_status_closure_report.py",
        },
        "mgt_g1_direct_residual_terminal_gate_report": {
            "scripts/build_mgt_g1_direct_residual_terminal_gate_report.py",
        },
        "paid_pilot_scope_guard_report": {
            "scripts/build_paid_pilot_scope_guard_report.py",
        },
        "phase1_core_api_contract": {
            "scripts/build_phase1_core_api_contract_artifacts.py",
        },
        "pm_release_gate_report": {
            "scripts/check_github_development_sync_preflight.py",
            "scripts/report_pm_release_gate.py",
        },
        "non_snapshot_product_surfaces": {
            "scripts/build_g1_f2g_f2h_cause_narrowing_status.py",
            "scripts/build_goal_bottleneck_roadmap_surface.py",
            "scripts/build_gpcr_hard_decoy_operator_intake_packet.py",
            "scripts/build_gpcr_hard_decoy_product_report.py",
            "scripts/build_phase3_large_model_runner_readiness_receipt.py",
            "scripts/build_phase6_benchmark_scale_status.py",
            "scripts/build_pocketmd_lite_product_surface.py",
            "scripts/build_product_capabilities_surface.py",
            "scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py",
            "scripts/materialize_gpcr_hard_decoy_suite_report.py",
            "scripts/materialize_pocketmd_lite_operator_intake_from_rows.py",
            "scripts/materialize_pocketmd_lite_topk_survival_report.py",
            "scripts/materialize_public_benchmark_pose_success_harness.py",
            "scripts/materialize_science_actual_closure_from_rows.py",
            "scripts/report_release_evidence_freshness.py",
            "src/structural_analysis/benchmark/acquisition.py",
        },
        "public_benchmark_source_of_truth": {
            "scripts/build_public_benchmark_operator_intake_packet.py",
            "scripts/build_public_benchmark_source_of_truth.py",
            "scripts/materialize_public_benchmark_harness_bundle.py",
            "scripts/materialize_public_benchmark_operator_bundle_from_rows.py",
        },
        "ux_new_user_observation_report": {
            "scripts/build_ux_new_user_observation_report.py",
        },
        "workstation_delivery_readiness": {
            "scripts/check_workstation_delivery_readiness.py",
        },
    }
    ignored_test_prefixes = ("tests/",)
    if path.startswith(ignored_test_prefixes):
        return False
    scoped_paths = artifact_specific_paths.get(artifact_name)
    globally_scoped_paths = set().union(*artifact_specific_paths.values())
    if path in globally_scoped_paths:
        return bool(scoped_paths is not None and path in scoped_paths)
    return True


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
        input_checksum = _first_present(
            payload,
            (
                "input_checksum",
                "input_checksums",
                "input_sha256",
                "input_artifact_checksum",
                "source_checksum",
            ),
        )
        source_state_fresh, source_state_kind, changed_paths = _source_state_freshness(
            artifact_name=name,
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
            "input_checksum_present": _truthy_presence(input_checksum),
            "source_commit_matches_head": bool(_commit_matches(source_commit, current_commit)),
            "source_state_fresh": source_state_fresh,
            "source_state_kind": source_state_kind,
            "changed_paths_since_source_commit": changed_paths,
            "metadata_complete": bool(generated_at and source_commit is not None and "reused_evidence" in payload),
        }
        rows.append(row)
    return rows


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _truthy_presence(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _schema_version_blockers(artifacts: dict[str, dict[str, Any]]) -> list[str]:
    return [
        f"schema_invalid:missing_schema_version:{name}"
        for name, payload in artifacts.items()
        if not payload.get("schema_version")
    ]


def _exact_schema_version_blockers(artifacts: dict[str, dict[str, Any]]) -> list[str]:
    expected = {
        "g1_full_load_hip_newton_lane_report": "g1-full-load-hip-newton-lane.v1",
    }
    blockers: list[str] = []
    for name, expected_schema in expected.items():
        payload = artifacts.get(name, {})
        schema = payload.get("schema_version")
        if schema and schema != expected_schema:
            blockers.append(f"schema_invalid:unexpected_schema_version:{name}")
    return blockers


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


def _completed_customer_shadow_row_count(rows: list[dict[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        if row.get("contract_pass") is True
        and str(row.get("project_status", "") or "") == "completed"
        and row.get("raw_data_retained_by_customer") is True
        and row.get("redistribution_allowed") is False
    )


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
    elif evidence.get("schema_version") != "g1-child-hip-residual-refresh-evidence.v1":
        blockers.append("child_hip_residual_refresh_evidence_schema_invalid")
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


def _g1_child_gate_summary(lane_payload: dict[str, Any]) -> dict[str, Any]:
    evidence = _as_dict(lane_payload.get("child_gate_evidence"))
    blockers = [str(item) for item in _as_list(evidence.get("blockers"))]
    if not evidence:
        blockers.append("child_gate_evidence_missing")
    elif evidence.get("schema_version") != "g1-child-gate-evidence.v1":
        blockers.append("child_gate_evidence_schema_invalid")
    for key, blocker in (
        ("direct_residual_newton_ready", "child_direct_residual_newton_ready_not_proven"),
        ("direct_residual_gate_passed", "child_direct_residual_gate_not_proven"),
        ("relative_increment_gate_passed", "child_relative_increment_gate_not_proven"),
        ("full_load_closure_passed", "child_full_load_closure_not_proven"),
        ("load_scale_passed", "child_observed_load_scale_below_required_full_load"),
        ("fallback_zero_passed", "child_fallback_zero_not_proven"),
        ("material_newton_breadth_passed", "child_material_newton_breadth_not_proven"),
        (
            "consistent_residual_jacobian_newton_passed",
            "child_consistent_residual_jacobian_newton_not_proven",
        ),
    ):
        if evidence.get(key) is not True:
            blockers.append(blocker)
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "ready": bool(evidence.get("ready") is True and not blockers),
        "blockers": blockers,
        "evidence": evidence,
    }


def _g1_hip_consistency_proof_summary(lane_payload: dict[str, Any]) -> dict[str, Any]:
    proof = _as_dict(lane_payload.get("hip_consistency_proof"))
    lane_source_commit = str(lane_payload.get("source_commit_sha", "") or "")
    proof_source_commit = str(proof.get("source_commit_sha", "") or "")
    proof_source_state_fresh = proof.get("source_state_fresh")
    proof_source_state_kind = str(proof.get("source_state_kind") or "")
    proof_changed_paths = [
        str(item) for item in _as_list(proof.get("changed_paths_since_source_commit"))
    ]
    receipt_blockers = [str(item) for item in _as_list(proof.get("receipt_blockers"))]
    runtime_blockers = [str(item) for item in _as_list(proof.get("runtime_blockers"))]
    worker = _as_dict(proof.get("production_rocm_hip_residual_jvp_worker"))
    worker_blockers = [str(item) for item in _as_list(worker.get("blockers"))]
    worker_residual_path_blockers = [
        str(item) for item in _as_list(worker.get("residual_jvp_worker_path_blockers"))
    ]
    worker_g1_closure_gate_blockers = [
        str(item) for item in _as_list(worker.get("g1_closure_gate_blockers"))
    ]
    blockers = [str(item) for item in _as_list(lane_payload.get("blockers"))]
    proof_blockers = [
        item for item in blockers if item.startswith("hip_consistency_proof")
    ]
    if not proof:
        proof_blockers.append("hip_consistency_proof_missing")
    if not proof_source_commit:
        proof_blockers.append("hip_consistency_proof_source_commit_sha_missing")
    elif (
        lane_source_commit
        and proof_source_commit != lane_source_commit
        and proof_source_state_fresh is not True
    ):
        proof_blockers.append("hip_consistency_proof_source_commit_sha_mismatch")
    if proof.get("reused_evidence") is not False:
        proof_blockers.append("hip_consistency_proof_reused_evidence_not_false")
    if proof.get("rocm_hip_required") is not True:
        proof_blockers.append("hip_consistency_proof_rocm_hip_not_required")
    if proof.get("cpu_diagnostic_assembler_used") is not False:
        proof_blockers.append("hip_consistency_proof_cpu_diagnostic_assembler_not_explicitly_false")
    if proof.get("production_hip_residual_jacobian_path") is not True:
        proof_blockers.append("hip_consistency_proof_production_hip_path_not_proven")
    if proof.get("consistent_residual_jacobian_newton_gate_passed") is not True:
        proof_blockers.append("hip_consistency_proof_gate_not_passed")
    if worker:
        if worker.get("residual_jvp_worker_path_ready") is False or worker_residual_path_blockers:
            proof_blockers.append(
                "hip_consistency_proof_residual_jvp_worker_path_not_ready"
            )
        elif (
            worker.get("residual_jvp_worker_path_ready") is not True
            and worker.get("ready") is not True
        ):
            proof_blockers.append(
                "hip_consistency_proof_production_rocm_hip_residual_jvp_worker_not_ready"
            )
        if worker.get("g1_closure_gate_ready") is False or worker_g1_closure_gate_blockers:
            proof_blockers.append("hip_consistency_proof_worker_g1_closure_gate_not_ready")
        proof_blockers.extend(
            f"hip_consistency_proof_worker::{item}" for item in worker_blockers
        )
    if receipt_blockers:
        proof_blockers.append("hip_consistency_proof_has_blockers")
    proof_blockers.extend(
        f"hip_consistency_proof_runtime::{item}" for item in runtime_blockers
    )
    proof_blockers = sorted(dict.fromkeys(proof_blockers))
    ready = bool(
        proof
        and proof.get("reused_evidence") is False
        and proof.get("rocm_hip_required") is True
        and proof.get("cpu_diagnostic_assembler_used") is False
        and proof.get("production_hip_residual_jacobian_path") is True
        and proof.get("consistent_residual_jacobian_newton_gate_passed") is True
        and not receipt_blockers
        and not runtime_blockers
        and not proof_blockers
    )
    return {
        "ready": ready,
        "blockers": proof_blockers,
        "path": str(proof.get("path", "")),
        "present": bool(proof.get("present")),
        "status": str(proof.get("status", "")),
        "source_commit_sha": proof_source_commit,
        "source_state_fresh": proof_source_state_fresh,
        "source_state_kind": proof_source_state_kind,
        "changed_paths_since_source_commit": proof_changed_paths,
        "reused_evidence": proof.get("reused_evidence"),
        "rocm_hip_required": proof.get("rocm_hip_required"),
        "execution_mode": proof.get("execution_mode"),
        "cpu_diagnostic_assembler_used": proof.get("cpu_diagnostic_assembler_used"),
        "production_hip_residual_jacobian_path": proof.get("production_hip_residual_jacobian_path"),
        "consistent_residual_jacobian_newton_gate_passed": proof.get(
            "consistent_residual_jacobian_newton_gate_passed"
        ),
        "production_rocm_hip_residual_jvp_worker": {
            "present": bool(worker),
            "ready": worker.get("ready") is True,
            "status": str(worker.get("status", "")),
            "worker_id": str(worker.get("worker_id", "")),
            "blockers": worker_blockers,
            "residual_jvp_worker_path_ready": worker.get(
                "residual_jvp_worker_path_ready"
            ),
            "residual_jvp_worker_path_blockers": worker_residual_path_blockers,
            "g1_closure_gate_ready": worker.get("g1_closure_gate_ready"),
            "g1_closure_gate_blockers": worker_g1_closure_gate_blockers,
        },
        "receipt_blockers": receipt_blockers,
        "runtime_blockers": runtime_blockers,
    }


def _g1_blocker_grouping_metadata(
    *,
    top_level_blockers: list[str],
    suppressed_detail_blockers: list[str],
) -> dict[str, Any]:
    root_groups = [
        {
            "root_blocker": "g1::full_load_gate_not_closed",
            "closure_dimension": "cpu_full_load_1_0_residual_increment_gate",
            "representative_detail_prefixes": (
                "g1_full_load_lane::checkpoint_load_scale_below_required_full_load",
                "g1_full_load_lane::child_full_load_closure_not_proven",
                "g1_full_load_lane::child_observed_load_scale_below_required_full_load",
                "g1_full_load_lane::full_load_input_not_pass",
                "g1_full_load_lane::observed_load_scale_below_required_full_load",
            ),
        },
        {
            "root_blocker": "g1::full_mesh_nonlinear_equilibrium_not_closed",
            "closure_dimension": "cpu_full_mesh_full_building_nonlinear_equilibrium",
            "representative_detail_prefixes": (
                "g1_full_mesh_full_load_not_closed",
                "g1_full_load_lane::child_direct_residual_gate_not_proven",
                "g1_full_load_lane::child_relative_increment_gate_not_proven",
                "g1_full_load_lane::child_direct_residual_newton_ready_not_proven",
            ),
        },
        {
            "root_blocker": "g1::material_newton_breadth_not_closed",
            "closure_dimension": "cpu_material_newton_consistent_residual_jacobian",
            "representative_detail_prefixes": (
                "g1_full_load_lane::child_consistent_residual_jacobian_newton_not_proven",
                "g1_full_load_lane::child_material_newton_breadth_not_proven",
                "g1_full_load_lane::child_fallback_zero_not_proven",
                "g1_full_load_lane::hip_consistency_proof_gate_not_passed",
                "g1_full_load_lane::hip_consistency_proof_worker_g1_closure_gate_not_ready",
                "g1_full_load_lane::hip_consistency_proof_worker::consistent_residual_jacobian_newton_gate_not_passed",
            ),
        },
        {
            "root_blocker": "g1::production_rocm_hip_residency_not_closed",
            "closure_dimension": "gpu_hip_followup_performance_and_residency",
            "representative_detail_prefixes": (
                "g1_full_load_lane::child_global_krylov_component_missing",
                "g1_full_load_lane::child_current_tangent_residual_row_component_missing",
                "g1_full_load_lane::hip_consistency_proof",
                "g1_full_load_lane::matrix_free_global_krylov",
                "g1_full_load_lane::current_tangent_residual_row_correction",
            ),
        },
    ]
    active_root_blockers = set(top_level_blockers)
    detail_by_root: dict[str, list[str]] = {group["root_blocker"]: [] for group in root_groups}
    unmatched_details: list[str] = []
    for detail in suppressed_detail_blockers:
        matched_root = ""
        for group in root_groups:
            prefixes = tuple(group["representative_detail_prefixes"])
            if any(detail.startswith(prefix) for prefix in prefixes):
                matched_root = str(group["root_blocker"])
                detail_by_root[matched_root].append(detail)
                break
        if not matched_root:
            unmatched_details.append(detail)
    return {
        "grouping_policy": (
            "G1 receipt/lane blockers are grouped under claim-dimension root blockers "
            "to avoid duplicate root status rows. Suppressed details remain visible, "
            "counted, and non-promoting."
        ),
        "root_blocker_count": len(top_level_blockers),
        "suppressed_detail_blocker_count": len(suppressed_detail_blockers),
        "detail_blockers_remain_visible": True,
        "grouping_promotes_status": False,
        "detail_blocker_represented_by_root_group": {
            detail: root
            for root, details in detail_by_root.items()
            for detail in details
        },
        "unmatched_detail_blockers": unmatched_details,
        "root_groups": [
            {
                "root_blocker": group["root_blocker"],
                "active": group["root_blocker"] in active_root_blockers,
                "closure_dimension": group["closure_dimension"],
                "represented_detail_blocker_count": len(
                    detail_by_root[str(group["root_blocker"])]
                ),
            }
            for group in root_groups
        ],
    }


def _g1_closure_boundary_metadata(
    *,
    g1_full_mesh_ready: bool,
    g1_full_load_lane_ready: bool,
    g1_lane_child_gate_ready: bool,
    g1_lane_hip_consistency_proof: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cpu_first_closure_scope": [
            "full_load_1_0",
            "full_mesh_full_building_nonlinear_equilibrium",
            "direct_residual_and_relative_increment_gates",
            "state_updated_material_newton_breadth",
            "consistent_residual_jacobian_newton",
            "fallback_zero_or_fully_traced_degraded_state",
        ],
        "gpu_hip_followup_scope": [
            "production_rocm_hip_residual_jacobian_path",
            "device_residency",
            "performance_scale",
            "cpu_gpu_parity_after_cpu_solver_gates",
        ],
        "claim_boundary": (
            "CPU full-load/full-mesh/material Newton closure is the numerical "
            "priority gate. GPU/HIP evidence is required for production residency, "
            "performance, and parity, but it does not replace CPU parity or close "
            "full G1 while the CPU numerical gates remain open."
        ),
        "gpu_hip_replaces_cpu_parity": False,
        "cpu_parity_required_before_gpu_performance_promotion": True,
        "metadata_promotes_status": False,
        "current_gate_state": {
            "full_mesh_full_load_ready": g1_full_mesh_ready,
            "full_load_hip_newton_lane_ready": g1_full_load_lane_ready,
            "child_cpu_gate_ready": g1_lane_child_gate_ready,
            "hip_consistency_proof_ready": bool(
                g1_lane_hip_consistency_proof.get("ready")
            ),
            "hip_residual_jvp_worker_path_ready": bool(
                _as_dict(
                    g1_lane_hip_consistency_proof.get(
                        "production_rocm_hip_residual_jvp_worker"
                    )
                ).get("residual_jvp_worker_path_ready")
            ),
            "hip_worker_g1_closure_gate_ready": bool(
                _as_dict(
                    g1_lane_hip_consistency_proof.get(
                        "production_rocm_hip_residual_jvp_worker"
                    )
                ).get("g1_closure_gate_ready")
            ),
        },
    }


def _workstation_delivery_summary(workstation: dict[str, Any]) -> dict[str, Any]:
    gates = [row for row in _as_list(workstation.get("gates")) if isinstance(row, dict)]
    passed_gate_count = sum(1 for row in gates if row.get("ok") is True)
    delivery_package = next(
        (
            row
            for row in gates
            if str(row.get("label", "")).lower() == "delivery package manifest"
        ),
        {},
    )
    required_sections = _as_dict(delivery_package.get("required_sections"))
    claim_boundary = _as_dict(workstation.get("claim_boundary"))
    forbidden = [str(item).lower() for item in _as_list(claim_boundary.get("forbidden"))]
    allowed = str(claim_boundary.get("allowed", "")).lower()
    acceptance_package_ready = bool(
        delivery_package.get("ok") is True
        and required_sections.get("ACCEPTANCE_PACKET.md") is True
        and delivery_package.get("manifest_acceptance_reference_pass") is True
    )
    engineer_review_boundary_ready = bool(
        "engineer review" in allowed
        and any("structural engineer replacement" in item for item in forbidden)
        and any("full autonomous replacement" in item for item in forbidden)
    )
    return {
        "gate_count": len(gates),
        "passed_gate_count": passed_gate_count,
        "all_gates_passed": bool(gates and passed_gate_count == len(gates)),
        "workstation_delivery_8_of_8": bool(len(gates) >= 8 and passed_gate_count >= 8),
        "acceptance_package_ready": acceptance_package_ready,
        "engineer_review_boundary_ready": engineer_review_boundary_ready,
        "claim_boundary": claim_boundary,
    }


def _root_blocker_stream(blocker: str) -> str:
    text = blocker.lower()
    if (
        text.startswith("stale_or_inconsistent:")
        or text.startswith("pm_release::github_sync::")
        or "github_sync" in text
        or "source_commit" in text
        or "input_checksum" in text
    ):
        return "release freshness/sync"
    if (
        text.startswith("ci_streak::")
        or text.startswith("self_hosted_runner::")
        or text.startswith("runner_policy::")
        or "basic_ci" in text
        or "ci_30" in text
        or "runner" in text
    ):
        return "CI runner/streak"
    if text.startswith("human_ux::") or "::ux::" in text:
        return "human UX"
    if text.startswith("license::") or "::security::license" in text:
        return "license/legal"
    if text.startswith("license_server::") or text.startswith("commercial_sla::"):
        return "license/legal"
    if text.startswith("customer_shadow::"):
        return "customer shadow"
    if text.startswith("external_benchmark::") or "external_receipt" in text or "external_submission" in text:
        return "external benchmark"
    if text.startswith("fresh_full_validation::"):
        return "fresh validation"
    if text.startswith("g1") or "::g1" in text or "residual_holdout" in text:
        return "G1 solver"
    return "release freshness/sync"


def _root_blockers(blockers: list[str]) -> dict[str, dict[str, Any]]:
    streams = (
        "release freshness/sync",
        "CI runner/streak",
        "human UX",
        "license/legal",
        "customer shadow",
        "external benchmark",
        "fresh validation",
        "G1 solver",
    )
    grouped: dict[str, list[str]] = {stream: [] for stream in streams}
    for blocker in blockers:
        grouped.setdefault(_root_blocker_stream(blocker), []).append(blocker)
    return {
        stream: {
            "blocked": bool(items),
            "blocker_count": len(items),
            "blockers": items,
        }
        for stream, items in grouped.items()
    }


PHASE0_BLOCKER_CATEGORY_BY_STREAM = {
    "G1 solver": "numerical",
    "external benchmark": "benchmark",
    "fresh validation": "benchmark",
    "release freshness/sync": "software product",
    "CI runner/streak": "software product",
    "human UX": "software product",
    "customer shadow": "future commercial",
    "license/legal": "future commercial",
}


PHASE0_BLOCKER_CATEGORY_DESCRIPTIONS = {
    "numerical": (
        "Solver math and deterministic equilibrium evidence: full mesh/load, residual, "
        "increment, Jacobian/material Newton, fallback-zero, and CPU/HIP parity."
    ),
    "benchmark": (
        "Reference corpus and validation evidence: external benchmark receipts, fresh "
        "validation receipts, and benchmark scorecard coverage."
    ),
    "software product": (
        "Developer Preview productization evidence: release freshness/sync, CI/runner "
        "streaks, generated artifact consistency, and human UX workflow observation."
    ),
    "future commercial": (
        "Commercial Release evidence kept outside the Developer Preview blocker bar: "
        "customer shadow projects, product/legal license approvals, license server/SLA "
        "style obligations, and related commercial accountability."
    ),
}


def _phase0_blocker_categories(
    root_blockers: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    categories = {
        category: {
            "blocked": False,
            "blocker_count": 0,
            "root_streams": [],
            "blockers": [],
            "description": PHASE0_BLOCKER_CATEGORY_DESCRIPTIONS[category],
        }
        for category in (
            "numerical",
            "benchmark",
            "software product",
            "future commercial",
        )
    }
    uncategorized: list[str] = []
    for stream, summary in root_blockers.items():
        category = PHASE0_BLOCKER_CATEGORY_BY_STREAM.get(stream)
        blockers = _as_list(summary.get("blockers")) if isinstance(summary, dict) else []
        if category is None:
            uncategorized.extend(blockers)
            continue
        row = categories[category]
        if blockers:
            row["blocked"] = True
            row["root_streams"].append(stream)
            row["blocker_count"] += len(blockers)
            row["blockers"].extend(blockers)
    if uncategorized:
        row = categories["software product"]
        row["blocked"] = True
        row["root_streams"].append("uncategorized")
        row["blocker_count"] += len(uncategorized)
        row["blockers"].extend(uncategorized)
    for row in categories.values():
        row["root_streams"] = sorted(dict.fromkeys(row["root_streams"]))
        row["blockers"] = sorted(dict.fromkeys(str(item) for item in row["blockers"]))
    return categories


def _gap_ledger_split_summary(rows: list[Any]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for ledger_name in ("commercial_solver", "ai_engine"):
        ledger_rows = [
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("ledger", "")) == ledger_name
        ]
        status_counts: dict[str, int] = {}
        nonclosed_ids: list[str] = []
        locally_closable_nonclosed_ids: list[str] = []
        for row in ledger_rows:
            status = str(row.get("status", ""))
            status_counts[status] = status_counts.get(status, 0) + 1
            closed = bool(row.get("closed") is True or status == "closed")
            row_id = str(row.get("id", ""))
            if not closed and row_id:
                nonclosed_ids.append(row_id)
                if row.get("locally_closable") is True:
                    locally_closable_nonclosed_ids.append(row_id)
        summary[ledger_name] = {
            "row_count": len(ledger_rows),
            "status_counts": dict(sorted(status_counts.items())),
            "nonclosed_row_ids": sorted(nonclosed_ids),
            "locally_closable_nonclosed_row_ids": sorted(locally_closable_nonclosed_ids),
        }
    return summary


def _gap_ledger_audit_split_summary(row_outcomes: list[Any]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for ledger_name in ("commercial_solver", "ai_engine"):
        rows = [
            row
            for row in row_outcomes
            if isinstance(row, dict) and str(row.get("ledger", "")) == ledger_name
        ]
        nonclosed_rows = [row for row in rows if row.get("closed") is not True]
        missing_evidence_ids = sorted(
            str(row.get("id", "")) for row in rows if row.get("evidence_present") is not True
        )
        missing_claim_boundary_ids = sorted(
            str(row.get("id", ""))
            for row in rows
            if row.get("claim_boundary_present") is not True
        )
        nonclosed_missing_blocker_ids = sorted(
            str(row.get("id", ""))
            for row in nonclosed_rows
            if _as_int(row.get("blocker_count"), 0) <= 0
        )
        closure_requirement_count = sum(
            _as_int(row.get("closure_requirement_count"), 0) for row in rows
        )
        closure_requirement_pass_count = sum(
            _as_int(row.get("closure_requirement_pass_count"), 0) for row in rows
        )
        closure_requirement_fail_count = sum(
            _as_int(row.get("closure_requirement_fail_count"), 0) for row in rows
        )
        nonclosed_rows_with_failed_closure_requirements = [
            row
            for row in nonclosed_rows
            if _as_int(row.get("closure_requirement_fail_count"), 0) > 0
        ]
        nonclosed_failed_closure_requirement_ids = sorted(
            f"{str(row.get('id', ''))}:{str(requirement_id)}"
            for row in nonclosed_rows_with_failed_closure_requirements
            for requirement_id in _as_list(row.get("closure_requirement_failed_ids"))
            if str(row.get("id", "")) and str(requirement_id)
        )
        summary[ledger_name] = {
            "row_count": len(rows),
            "closed_row_count": sum(1 for row in rows if row.get("closed") is True),
            "nonclosed_row_count": len(nonclosed_rows),
            "evidence_present_count": len(rows) - len(missing_evidence_ids),
            "claim_boundary_present_count": len(rows) - len(missing_claim_boundary_ids),
            "nonclosed_rows_with_blockers_count": (
                len(nonclosed_rows) - len(nonclosed_missing_blocker_ids)
            ),
            "closure_requirement_count": closure_requirement_count,
            "closure_requirement_pass_count": closure_requirement_pass_count,
            "closure_requirement_fail_count": closure_requirement_fail_count,
            "nonclosed_rows_with_failed_closure_requirements_count": len(
                nonclosed_rows_with_failed_closure_requirements
            ),
            "missing_evidence_ids": [item for item in missing_evidence_ids if item],
            "missing_claim_boundary_ids": [
                item for item in missing_claim_boundary_ids if item
            ],
            "nonclosed_missing_blocker_ids": [
                item for item in nonclosed_missing_blocker_ids if item
            ],
            "nonclosed_failed_closure_requirement_ids": (
                nonclosed_failed_closure_requirement_ids
            ),
        }
    return summary


def _developer_preview_closure_visibility_summary(
    developer_preview: dict[str, Any],
) -> dict[str, Any]:
    visibility = _as_dict(developer_preview.get("gap_ledger_closure_requirement_visibility"))
    return {
        "source_status": str(visibility.get("source_status", "missing")),
        "source_contract_pass": bool(visibility.get("source_contract_pass") is True),
        "source_full_gap_ledger_ready": bool(
            visibility.get("source_full_gap_ledger_ready") is True
        ),
        "ai_engine_guardrail_rows_ready": bool(
            visibility.get("ai_engine_guardrail_rows_ready") is True
        ),
        "autonomous_ai_engine_claim_ready": bool(
            visibility.get("autonomous_ai_engine_claim_ready") is True
        ),
        "autonomous_ai_engine_claim_blockers": [
            str(item)
            for item in _as_list(visibility.get("autonomous_ai_engine_claim_blockers"))
            if str(item)
        ],
        "closure_requirement_count": _as_int(
            visibility.get("closure_requirement_count"), 0
        ),
        "closure_requirement_pass_count": _as_int(
            visibility.get("closure_requirement_pass_count"), 0
        ),
        "closure_requirement_fail_count": _as_int(
            visibility.get("closure_requirement_fail_count"), 0
        ),
        "nonclosed_rows_with_failed_closure_requirements_count": _as_int(
            visibility.get("nonclosed_rows_with_failed_closure_requirements_count"), 0
        ),
        "nonclosed_failed_closure_requirement_ids": [
            str(item)
            for item in _as_list(visibility.get("nonclosed_failed_closure_requirement_ids"))
            if str(item)
        ],
        "claim_boundary": str(visibility.get("claim_boundary", "")),
    }


def _developer_preview_scope_boundary_summary(
    developer_preview: dict[str, Any],
) -> dict[str, Any]:
    sync = _as_dict(developer_preview.get("scope_boundary_sync"))
    gui = _as_dict(sync.get("gui_surface"))
    reports = _as_dict(_as_dict(sync.get("surface_groups")).get("reports"))
    doc_surfaces = _as_dict(sync.get("doc_surfaces"))
    return {
        "status": str(sync.get("status", "missing")),
        "contract_pass": bool(sync.get("contract_pass") is True),
        "doc_surface_count": len(doc_surfaces),
        "doc_surface_pass_count": sum(
            1 for row in doc_surfaces.values() if _as_dict(row).get("contract_pass") is True
        ),
        "report_surface_count": _as_int(reports.get("surface_count"), 0),
        "report_surface_pass_count": _as_int(reports.get("contract_pass_count"), 0),
        "gui_contract_pass": bool(gui.get("contract_pass") is True),
        "gui_consumes_scope_record": bool(gui.get("consumes_scope_record") is True),
        "gui_consumes_closure_visibility_record": bool(
            gui.get("consumes_closure_visibility_record") is True
        ),
        "gui_consumes_failed_closure_requirement_ids": bool(
            gui.get("consumes_failed_closure_requirement_ids") is True
        ),
        "gui_renders_closure_requirement_summary": bool(
            gui.get("renders_closure_requirement_summary") is True
        ),
        "gui_renders_closure_visibility_boundary": bool(
            gui.get("renders_closure_visibility_boundary") is True
        ),
    }


def _deduplicate_pm_release_blockers(
    pm_blockers: list[str],
    *,
    ux_human_ready: bool,
    ux_blockers: list[str],
) -> list[str]:
    if ux_human_ready or not ux_blockers:
        return pm_blockers
    return [item for item in pm_blockers if item not in PM_RELEASE_UX_DUPLICATE_WRAPPERS]


def _suppressed_pm_release_duplicate_blockers(
    pm_blockers: list[str],
    *,
    ux_human_ready: bool,
    ux_blockers: list[str],
) -> list[str]:
    if ux_human_ready or not ux_blockers:
        return []
    return [item for item in pm_blockers if item in PM_RELEASE_UX_DUPLICATE_WRAPPERS]


def _representative_human_ux_blockers(ux_blockers: list[str]) -> tuple[list[str], list[str]]:
    if "observation_file_missing" not in ux_blockers:
        return ux_blockers, []
    detail_blockers = [item for item in ux_blockers if item != "observation_file_missing"]
    return ["observation_file_missing"], detail_blockers


def _phase1_core_api_summary(phase1_core_api: dict[str, Any]) -> dict[str, Any]:
    cli_contract = _as_dict(phase1_core_api.get("cli_contract"))
    reference_contract = _as_dict(phase1_core_api.get("reference_validation_contract"))
    schema_validation = _as_dict(phase1_core_api.get("schema_validation"))
    return {
        "status": str(phase1_core_api.get("status", "missing")),
        "contract_pass": bool(phase1_core_api.get("contract_pass")),
        "claim_boundary_version": str(phase1_core_api.get("claim_boundary_version", "")),
        "invocation_surfaces": _as_list(phase1_core_api.get("invocation_surfaces")),
        "supported_preview_analysis_types": _as_list(
            phase1_core_api.get("supported_preview_analysis_types")
        ),
        "schema_validation_pass": bool(schema_validation.get("contract_pass")),
        "cli_contract_pass": bool(cli_contract.get("contract_pass")),
        "cli_same_result_schema_as_python_api": bool(
            cli_contract.get("same_result_schema_as_python_api")
        ),
        "cli_same_validation_report_schema_as_python_api": bool(
            cli_contract.get("same_validation_report_schema_as_python_api")
        ),
        "reference_validation_contract_pass": bool(reference_contract.get("contract_pass")),
        "python_api_blocks_reference_mismatch": bool(
            reference_contract.get("python_api_blocks_reference_mismatch")
        ),
        "cli_blocks_reference_mismatch": bool(
            reference_contract.get("cli_blocks_reference_mismatch")
        ),
        "unsupported_feature_count": _as_int(
            phase1_core_api.get("unsupported_feature_count"), 0
        ),
        "developer_preview_blocked_field_count": _as_int(
            phase1_core_api.get("developer_preview_blocked_field_count"), 0
        ),
        "claim_boundary": str(phase1_core_api.get("claim_boundary", "")),
        "ready": bool(phase1_core_api.get("contract_pass")),
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


def _engine_version_from_identity(identity: dict[str, Any]) -> str:
    package = _as_dict(identity.get("package_json"))
    pyproject = _as_dict(identity.get("pyproject"))
    package_name = str(package.get("name", ""))
    package_version = str(package.get("version", ""))
    pyproject_name = str(pyproject.get("name", ""))
    pyproject_version = str(pyproject.get("version", ""))
    name = package_name or pyproject_name or "unknown-product"
    version = package_version or pyproject_version or "unknown-version"
    return f"{name}@{version}"


def build_snapshot(
    *,
    repo_root: Path = ROOT,
    paths: SnapshotInputPaths = SnapshotInputPaths(),
    source_commit_sha: str | None = None,
    additional_receipt_paths: tuple[Path, ...] = (),
) -> dict[str, Any]:
    blockers: list[str] = []
    repo_root = repo_root.resolve()
    current_commit = source_commit_sha if source_commit_sha is not None else _git_head(repo_root)
    allowed_receipt_paths = _receipt_commit_allowed_paths(
        paths,
        repo_root=repo_root,
        additional_paths=additional_receipt_paths,
    )
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
    commercial_gap_ledger_status = _load_json(repo_root, paths.commercial_gap_ledger_status, blockers)
    gap_ledger_evidence_audit = _load_json(repo_root, paths.gap_ledger_evidence_audit, blockers)
    phase1_core_api = _load_json(repo_root, paths.phase1_core_api_contract, blockers)
    developer_preview = _load_json(repo_root, paths.developer_preview_readiness, blockers)
    developer_preview_rc = _load_json(repo_root, paths.developer_preview_rc_status, blockers)
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
    scope_guard = _load_json(repo_root, paths.paid_pilot_scope_guard, blockers)
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
    phase3_release_control_cleanup_plan = _load_json(
        repo_root,
        paths.phase3_release_control_cleanup_plan,
        blockers,
    )
    self_hosted_runner_status = _load_json(repo_root, paths.self_hosted_runner_status, blockers)
    runner_policy = check_runner_policy(
        workflow_dir=_resolve(repo_root, paths.github_workflows)
    )

    release_area_green, release_area_total = _release_area_counts_from_pm(pm_report)
    gap_ledger_rows = _as_list(commercial_gap_ledger_status.get("rows"))
    gap_ledger_split_summary = _gap_ledger_split_summary(gap_ledger_rows)
    gap_ledger_audit_split_summary = _gap_ledger_audit_split_summary(
        _as_list(gap_ledger_evidence_audit.get("row_outcomes"))
    )
    ai_engine_split = _as_dict(gap_ledger_split_summary.get("ai_engine"))
    ai_engine_status_counts = _as_dict(ai_engine_split.get("status_counts"))
    ai_engine_guardrail_rows_ready = bool(
        commercial_gap_ledger_status.get("ai_engine_guardrail_rows_ready") is True
        or (
            "ai_engine_guardrail_rows_ready" not in commercial_gap_ledger_status
            and _as_int(ai_engine_split.get("row_count"), 0) > 0
            and _as_int(ai_engine_status_counts.get("closed"), 0)
            == _as_int(ai_engine_split.get("row_count"), 0)
        )
    )
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
        "commercial_gap_ledger_status": commercial_gap_ledger_status,
        "gap_ledger_evidence_audit": gap_ledger_evidence_audit,
        "phase1_core_api_contract": phase1_core_api,
        "developer_preview_readiness": developer_preview,
        "developer_preview_rc_status": developer_preview_rc,
        "fresh_full_validation_lane_status": fresh,
        "mgt_g1_direct_residual_terminal_gate_report": g1,
        "g1_full_load_hip_newton_lane_report": g1_full_load_lane,
        "customer_shadow_evidence_status": customer,
        "workstation_delivery_readiness": workstation,
        "independent_product_readiness": independent,
        "github_actions_ci_streak_evidence": ci_streak,
        "ux_new_user_observation_report": ux_new_user,
        "license_status_closure_report": license_status,
        "paid_pilot_scope_guard_report": scope_guard,
        "external_benchmark_submission_readiness": external_benchmark_readiness,
        "external_benchmark_submission_updates": external_benchmark_updates,
    }
    schema_artifacts = {
        **metadata_artifacts,
        "github_actions_runner_policy": runner_policy,
        "github_actions_self_hosted_runner_status": self_hosted_runner_status,
    }
    schema_blockers = [
        *_schema_version_blockers(schema_artifacts),
        *_exact_schema_version_blockers(schema_artifacts),
    ]
    blockers.extend(schema_blockers)
    metadata_rows = _metadata_rows(
        artifacts=metadata_artifacts,
        repo_root=repo_root,
        current_commit=current_commit,
        allowed_receipt_paths=allowed_receipt_paths,
    )
    enforce_input_checksums = source_commit_sha is None
    for row in metadata_rows:
        if not row["metadata_complete"]:
            blockers.append(f"stale_or_inconsistent:metadata_incomplete:{row['artifact']}")
        elif not row["source_state_fresh"]:
            blockers.append(f"stale_or_inconsistent:source_commit_mismatch:{row['artifact']}")
        if enforce_input_checksums and not row["input_checksum_present"]:
            blockers.append(f"stale_or_inconsistent:input_checksum_missing:{row['artifact']}")

    ux_summary = _as_dict(ux_new_user.get("summary"))
    ux_completion = ux_summary.get("completion_minutes")
    ux_max_minutes = ux_summary.get("max_completion_minutes", 30.0)
    ux_blockers = _as_list(ux_new_user.get("blockers"))
    ux_human_ready = bool(
        _contract_pass(ux_new_user)
        and ux_completion is not None
        and _as_float(ux_completion, default=999999.0) <= _as_float(ux_max_minutes, default=30.0)
        and not ux_blockers
    )
    ux_top_level_blockers, ux_suppressed_detail_blockers = _representative_human_ux_blockers(
        ux_blockers
    )

    pm_release_ready = bool(
        pm_report.get("limited_commercial_release_ready")
        and pm_report.get("release_area_gate_ready")
        and pm_report.get("full_release_gate_ready")
    )
    pm_release_decision = _as_dict(pm_report.get("release_decision"))
    pm_full_blockers = [str(item) for item in _as_list(pm_report.get("full_release_blockers"))]
    release_area_blockers = [str(item) for item in _as_list(pm_report.get("release_area_blockers"))]
    original_pm_blockers = pm_full_blockers or release_area_blockers
    suppressed_pm_release_duplicate_blockers = _suppressed_pm_release_duplicate_blockers(
        original_pm_blockers,
        ux_human_ready=ux_human_ready,
        ux_blockers=ux_blockers,
    )
    if not pm_release_ready:
        pm_blockers = _deduplicate_pm_release_blockers(
            original_pm_blockers,
            ux_human_ready=ux_human_ready,
            ux_blockers=ux_blockers,
        )
        blockers.extend(f"pm_release::{item}" for item in pm_blockers)
        if not original_pm_blockers:
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
    fresh_blockers = [str(item) for item in _as_list(fresh.get("blockers"))]
    fresh_lane_ids = {str(row.get("lane_id")) for row in fresh_rows if row.get("lane_id")}
    fresh_has_explicit_lane_blockers = any(
        item.split("::", 1)[0] in fresh_lane_ids for item in fresh_blockers
    )
    fresh_rows_ready = bool(
        len(fresh_rows) >= lane_count
        and fresh_row_pass_count >= lane_count
        and fresh_row_fresh_count >= lane_count
        and fresh_row_contract_count >= lane_count
    )
    fresh_ready = bool(
        _contract_pass(fresh)
        and lane_count > 0
        and fresh_receipts >= lane_count
        and fresh_present >= lane_count
        and fresh_rows_ready
    )
    if not fresh_ready:
        blockers.extend(f"fresh_full_validation::{item}" for item in fresh_blockers)
        if len(fresh_rows) < lane_count:
            blockers.append("fresh_full_validation::row_count_below_lane_count")
        if (
            fresh_rows
            and fresh_row_pass_count < lane_count
            and not fresh_has_explicit_lane_blockers
        ):
            blockers.append("fresh_full_validation::row_pass_count_below_lane_count")
        if (
            fresh_rows
            and fresh_row_fresh_count < lane_count
            and not fresh_has_explicit_lane_blockers
        ):
            blockers.append("fresh_full_validation::row_fresh_receipt_count_below_lane_count")
        if (
            fresh_rows
            and fresh_row_contract_count < lane_count
            and not fresh_has_explicit_lane_blockers
        ):
            blockers.append("fresh_full_validation::row_contract_pass_count_below_lane_count")
        if not fresh_blockers:
            blockers.append("fresh_full_validation:not_ready")

    customer_summary = _as_dict(customer.get("summary"))
    completed_shadow_cases = _as_int(customer_summary.get("completed_shadow_case_count"), 0)
    min_shadow_cases = _as_int(customer_summary.get("min_completed_shadow_cases"), 3)
    customer_rows = [
        row for row in _as_list(customer.get("evidence_rows")) if isinstance(row, dict)
    ]
    completed_customer_rows = _completed_customer_shadow_row_count(customer_rows)
    customer_rows_ready = bool(
        len(customer_rows) >= min_shadow_cases
        and completed_customer_rows >= min_shadow_cases
    )
    customer_ready = bool(
        _contract_pass(customer)
        and completed_shadow_cases >= min_shadow_cases
        and customer_rows_ready
    )
    if not customer_ready:
        blockers.extend(f"customer_shadow::{item}" for item in _as_list(customer.get("blockers")))
        if len(customer_rows) < min_shadow_cases:
            blockers.append("customer_shadow::evidence_row_count_below_minimum")
        if completed_customer_rows < min_shadow_cases:
            blockers.append("customer_shadow::completed_evidence_row_count_below_minimum")
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

    if not ux_human_ready:
        blockers.extend(f"human_ux::{item}" for item in ux_top_level_blockers)
        if not ux_top_level_blockers:
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
    commercial_future_scope_ready = bool(
        (
            pm_report.get("limited_commercial_ready")
            or pm_report.get("limited_commercial_release_ready")
        )
        and pm_report.get("ga_enterprise_ready")
    )
    if not commercial_future_scope_ready:
        blockers.extend(
            (
                "commercial_sla::production_support_commitment_missing",
                "license_server::operation_readiness_missing",
            )
        )

    scope_guard_checks = _as_dict(scope_guard.get("checks"))
    supported_scope_guard_ready = bool(
        _contract_pass(scope_guard)
        and not _as_list(scope_guard.get("blockers"))
        and all(value is True for value in scope_guard_checks.values())
    )
    if not supported_scope_guard_ready:
        scope_blockers = _as_list(scope_guard.get("blockers"))
        blockers.extend(f"assisted_service_scope::{item}" for item in scope_blockers)
        if not scope_blockers:
            blockers.append("assisted_service_scope:not_ready")

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
        and external_benchmark_receipts["update_count"] >= external_benchmark_receipts["queue_count"]
        and external_benchmark_receipts["update_attached_count"] >= external_benchmark_receipts["queue_count"]
        and external_benchmark_receipts["pending_count"] == 0
    )
    if not external_benchmark_ready:
        if not external_benchmark_updates_fresh:
            blockers.append("external_benchmark::submission_updates_reused_evidence_not_fresh")
        if external_benchmark_receipts["update_count"] < external_benchmark_receipts["queue_count"]:
            blockers.append("external_benchmark::submission_update_rows_below_queue_count")
        if external_benchmark_receipts["update_attached_count"] < external_benchmark_receipts["queue_count"]:
            blockers.append("external_benchmark::submission_update_receipts_below_queue_count")
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
    g1_root_blockers = [
        f"g1::{item}" for item in _as_list(g1.get("full_g1_closure_blockers"))
    ]
    g1_suppressed_detail_blockers: list[str] = []
    if not g1_full_mesh_ready:
        g1_suppressed_detail_blockers.append("g1_full_mesh_full_load_not_closed")
        blockers.extend(g1_root_blockers)
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
    g1_lane_child_gate = _g1_child_gate_summary(g1_full_load_lane)
    g1_lane_child_gate_ready = bool(g1_lane_child_gate["ready"])
    g1_lane_hip_consistency_proof = _g1_hip_consistency_proof_summary(
        g1_full_load_lane
    )
    g1_full_load_lane_ready = bool(
        _contract_pass(g1_full_load_lane)
        and str(g1_full_load_lane.get("status", "")).lower() == "ready"
        and g1_lane_reused_ok
        and g1_lane_full_load_input_pass
        and g1_lane_load_scale_pass
        and g1_lane_child_hip_refresh_ready
        and g1_lane_child_gate_ready
        and bool(g1_lane_hip_consistency_proof["ready"])
        and not _as_list(g1_full_load_lane.get("blockers"))
    )
    if not g1_full_load_lane_ready:
        lane_blockers = _as_list(g1_full_load_lane.get("blockers"))
        g1_suppressed_detail_blockers.extend(
            f"g1_full_load_lane::{item}" for item in lane_blockers
        )
        g1_suppressed_detail_blockers.extend(
            f"g1_full_load_lane::{item}"
            for item in _as_list(g1_lane_child_hip_refresh.get("blockers"))
        )
        g1_suppressed_detail_blockers.extend(
            f"g1_full_load_lane::{item}"
            for item in _as_list(g1_lane_child_gate.get("blockers"))
        )
        g1_suppressed_detail_blockers.extend(
            f"g1_full_load_lane::{item}"
            for item in _as_list(g1_lane_hip_consistency_proof.get("blockers"))
        )
        if not g1_lane_reused_ok:
            g1_suppressed_detail_blockers.append("g1_full_load_lane::reused_evidence_not_false")
        if not g1_lane_full_load_input_pass:
            g1_suppressed_detail_blockers.append("g1_full_load_lane::full_load_input_not_pass")
        if not g1_lane_load_scale_pass:
            g1_suppressed_detail_blockers.append(
                "g1_full_load_lane::observed_load_scale_below_required_full_load"
            )
        if not lane_blockers:
            g1_suppressed_detail_blockers.append("g1_full_load_lane:not_ready")
    g1_suppressed_detail_blockers = sorted(dict.fromkeys(g1_suppressed_detail_blockers))
    if not g1_root_blockers and (not g1_full_mesh_ready or not g1_full_load_lane_ready):
        blockers.append("g1::full_load_gate_not_closed")

    workstation_delivery_ready = bool(
        _contract_pass(workstation) and not _as_list(workstation.get("blockers"))
    )
    workstation_summary = _workstation_delivery_summary(workstation)
    if not workstation_delivery_ready:
        blockers.extend(f"workstation_delivery::{item}" for item in _as_list(workstation.get("blockers")))
    if not workstation_summary["workstation_delivery_8_of_8"]:
        blockers.append("workstation_delivery::workstation_delivery_8_of_8_not_ready")
    if not workstation_summary["acceptance_package_ready"]:
        blockers.append("workstation_delivery::acceptance_package_not_ready")
    if not workstation_summary["engineer_review_boundary_ready"]:
        blockers.append("workstation_delivery::engineer_review_claim_boundary_not_ready")
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
        and not schema_blockers
    )
    if not schema_valid:
        blockers.append("schema_invalid:required_snapshot_inputs_missing")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if str(item)))
    stale_or_inconsistent = any(item.startswith("stale_or_inconsistent:") for item in blockers)
    snapshot_source_state_consistent = bool(schema_valid and not stale_or_inconsistent)
    evidence_fresh = snapshot_source_state_consistent
    github_sync_clean = not any(
        str(item).startswith("pm_release::github_sync::") for item in blockers
    )
    full_quality_ready = bool(pm_release_ready)
    assisted_service_pilot_ready = bool(
        schema_valid
        and evidence_fresh
        and workstation_delivery_ready
        and workstation_summary["workstation_delivery_8_of_8"]
        and supported_scope_guard_ready
        and full_quality_ready
        and github_sync_clean
        and ux_human_ready
        and license_ready
        and workstation_summary["acceptance_package_ready"]
        and workstation_summary["engineer_review_boundary_ready"]
    )
    assisted_service_pilot_blockers = [
        label
        for label, ready in (
            ("schema_invalid", schema_valid),
            ("snapshot_source_state_not_consistent", snapshot_source_state_consistent),
            ("workstation_delivery_not_ready", workstation_delivery_ready),
            ("workstation_delivery_8_of_8_not_ready", workstation_summary["workstation_delivery_8_of_8"]),
            ("supported_scope_guard_not_ready", supported_scope_guard_ready),
            ("full_quality_not_ready", full_quality_ready),
            ("github_sync_not_clean", github_sync_clean),
            ("human_ux_observation_not_ready", ux_human_ready),
            ("license_approval_not_ready", license_ready),
            ("acceptance_package_not_ready", workstation_summary["acceptance_package_ready"]),
            ("engineer_review_boundary_not_ready", workstation_summary["engineer_review_boundary_ready"]),
        )
        if not ready
    ]
    solver_product_pilot_ready = bool(
        schema_valid
        and evidence_fresh
        and independent_product_ready
        and g1_full_mesh_ready
        and g1_full_load_lane_ready
        and external_benchmark_ready
        and customer_ready
        and fresh_ready
    )
    solver_product_blockers = [
        label
        for label, ready in (
            ("schema_invalid", schema_valid),
            ("snapshot_source_state_not_consistent", snapshot_source_state_consistent),
            ("independent_product_not_ready", independent_product_ready),
            ("g1_full_mesh_full_load_not_ready", g1_full_mesh_ready),
            ("g1_full_load_hip_newton_lane_not_ready", g1_full_load_lane_ready),
            ("external_benchmark_4_of_4_not_ready", external_benchmark_ready),
            ("customer_shadow_3_of_3_not_ready", customer_ready),
            ("fresh_validation_8_of_8_not_ready", fresh_ready),
        )
        if not ready
    ]
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
    limited_commercial_ready = bool(
        assisted_service_pilot_ready
        and solver_product_pilot_ready
        and (
            pm_report.get("limited_commercial_ready")
            or pm_report.get("limited_commercial_release_ready")
        )
    )
    ga_enterprise_ready = bool(
        limited_commercial_ready
        and independent_product_ready
        and pm_report.get("ga_enterprise_ready")
    )
    release_ready = bool(paid_pilot_ready and not blockers)
    status = "ready" if release_ready else ("stale_or_inconsistent" if stale_or_inconsistent else "blocked")
    root_blockers = _root_blockers(blockers)
    blocker_categories = _phase0_blocker_categories(root_blockers)
    phase3_cleanup_handoff = _as_dict(
        phase3_release_control_cleanup_plan.get("human_handoff")
    )
    github_sync_blockers = [
        item for item in blockers if str(item).startswith("pm_release::github_sync::")
    ]
    release_control_cleanup_component = {
        "local_worktree_dirty": worktree_dirty,
        "dirty_path_count": len(worktree_non_receipt_dirty_paths),
        "non_receipt_dirty_path_count": len(worktree_non_receipt_dirty_paths),
        "remote_github_sync_clean": github_sync_clean,
        "remote_github_sync_blocker_count": len(github_sync_blockers),
        "remote_github_sync_blockers": github_sync_blockers,
        "cleanup_plan_status": phase3_release_control_cleanup_plan.get("status", "missing"),
        "cleanup_plan_contract_pass": bool(phase3_release_control_cleanup_plan.get("contract_pass")),
        "cleanup_plan_candidate_set_source": phase3_release_control_cleanup_plan.get(
            "candidate_set_source", ""
        ),
        "cleanup_plan_candidate_set_scope": phase3_release_control_cleanup_plan.get(
            "candidate_set_scope", ""
        ),
        "cleanup_plan_current_worktree_diagnostics_included": bool(
            phase3_release_control_cleanup_plan.get("current_worktree_diagnostics_included")
        ),
        "cleanup_plan_current_worktree_diagnostic_source": (
            phase3_release_control_cleanup_plan.get("current_worktree_diagnostic_source", "")
        ),
        "cleanup_plan_candidate_path_count": phase3_release_control_cleanup_plan.get(
            "candidate_release_control_commit_set_count",
            0,
        ),
        "cleanup_plan_track_or_add_required_path_count": len(
            _as_list(phase3_release_control_cleanup_plan.get("track_or_add_required_paths"))
        ),
        "cleanup_plan_resolve_or_commit_dirty_tracked_path_count": len(
            _as_list(phase3_release_control_cleanup_plan.get("resolve_or_commit_dirty_tracked_paths"))
        ),
        "cleanup_plan_path_role_counts": phase3_release_control_cleanup_plan.get("path_role_counts", {}),
        "cleanup_plan_recommended_action_counts": phase3_release_control_cleanup_plan.get(
            "recommended_action_counts",
            {},
        ),
        "human_git_action_required": bool(
            phase3_release_control_cleanup_plan.get("human_git_action_required")
        ),
        "codex_commit_or_push_performed": bool(
            phase3_release_control_cleanup_plan.get("codex_commit_or_push_performed")
        ),
        "human_handoff_status": phase3_cleanup_handoff.get("status", ""),
        "human_handoff_next_action": phase3_cleanup_handoff.get("next_action", ""),
        "human_handoff_suggested_command_count": len(
            _as_list(phase3_cleanup_handoff.get("suggested_local_command_args"))
        ),
        "human_handoff_push_or_release_command_included": bool(
            phase3_cleanup_handoff.get("push_or_release_command_included")
        ),
        "claim_boundary": (
            "Local release-control cleanup and remote GitHub sync are separate blockers. "
            "Suggested local git commands are human handoff only; Codex has not committed, "
            "pushed, released, or mutated remote refs."
        ),
    }
    aggregator_source_artifacts = _snapshot_source_artifacts(repo_root, paths)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": current_commit,
        "engine_version": _engine_version_from_identity(identity),
        "input_checksums": _snapshot_input_checksums(
            repo_root,
            paths,
        ),
        "reused_evidence": False,
        "reuse_policy": AGGREGATOR_REUSE_POLICY,
        "aggregator_freshness_policy": {
            "mode": "direct_aggregator_source_tracking",
            "source_artifact_count": len(aggregator_source_artifacts),
            "source_artifacts": aggregator_source_artifacts,
            "claim_boundary": (
                "This readiness rollup does not rerun upstream release gates. It exposes "
                "source commit and input checksums for every direct upstream artifact so "
                "stale readiness snapshots can be detected without treating the rollup as "
                "a leaf validation receipt."
            ),
        },
        "schema_valid": schema_valid,
        "evidence_fresh": evidence_fresh,
        "snapshot_source_state_consistent": snapshot_source_state_consistent,
        "stale_or_inconsistent": stale_or_inconsistent,
        "workstation_delivery_ready": workstation_delivery_ready,
        "assisted_service_pilot_ready": assisted_service_pilot_ready,
        "solver_product_pilot_ready": solver_product_pilot_ready,
        "limited_commercial_ready": limited_commercial_ready,
        "paid_pilot_ready": paid_pilot_ready,
        "independent_product_ready": independent_product_ready,
        "ga_enterprise_ready": ga_enterprise_ready,
        "release_ready": release_ready,
        "release_decision": pm_release_decision,
        "status": status,
        "reason_code": "PASS" if release_ready else status.upper(),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "root_blockers": root_blockers,
        "blocker_categories": blocker_categories,
        "claim_boundary": {
            "assisted_service_pilot": (
                "assisted_service_pilot_ready is the engineer-review workstation service track. "
                "It requires workstation delivery 8/8, supported-scope guard, full quality, clean "
                "GitHub sync, real human UX observation, product/legal license approval, acceptance "
                "package, and explicit proxy/fallback/engineer-review boundaries. It does not relax "
                "solver_product gates."
            ),
            "solver_product": (
                "solver_product_pilot_ready keeps the independent solver-product bar: G1 full "
                "mesh/load 1.0 with residual+increment/material Newton/Jacobian/fallback-zero and "
                "production HIP evidence, EB 4/4, customer shadow 3/3, and fresh validation 8/8."
            ),
            "paid_pilot": (
                "paid_pilot_ready requires a clean canonical snapshot, full PM release-area gate, "
                "tracked CI streaks, human new-user observation, product/legal license closure, EB "
                "receipts, customer shadow minimum, fresh validation receipts, and full-mesh/full-load "
                "G1 closure."
            ),
            "contract_pass_vs_release_ready": (
                "Upstream contract_pass fields are component contract results. They are not treated as "
                "release_ready when release-area, snapshot source-state consistency, customer, "
                "fresh-validation, or G1 blockers remain."
            ),
            "gap_ledger_evidence_audit": str(gap_ledger_evidence_audit.get("claim_boundary", "")),
            "commercial_gap_ledger_status": (
                "This component summarizes current G1-G10 and AI-G1-AI-G10 ledger row status. "
                "Open, partial, external-blocked, or autonomous-AI-claim blocked rows remain "
                "blockers and are not converted into release readiness by this snapshot. "
                "AI guardrail row closure is separate from autonomous AI engine claim closure."
            ),
            "phase1_core_api_contract": str(phase1_core_api.get("claim_boundary", "")),
            "developer_preview_readiness": str(developer_preview.get("claim_boundary", "")),
            "developer_preview_rc": str(developer_preview_rc.get("claim_boundary", "")),
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
                "release_decision": pm_release_decision,
                "suppressed_duplicate_blocker_count": len(
                    suppressed_pm_release_duplicate_blockers
                ),
                "suppressed_duplicate_blockers": [
                    f"pm_release::{item}"
                    for item in suppressed_pm_release_duplicate_blockers
                ],
                "duplicate_blocker_represented_by": {
                    f"pm_release::{item}": "human_ux::*"
                    for item in suppressed_pm_release_duplicate_blockers
                },
            },
            "commercial_gap_ledger_status": {
                "status": str(commercial_gap_ledger_status.get("status", "missing")),
                "commercial_solver_gap_ready": bool(
                    commercial_gap_ledger_status.get("commercial_solver_gap_ready")
                ),
                "ai_engine_guardrail_rows_ready": ai_engine_guardrail_rows_ready,
                "ai_engine_gap_ready": bool(commercial_gap_ledger_status.get("ai_engine_gap_ready")),
                "autonomous_ai_engine_claim_ready": bool(
                    commercial_gap_ledger_status.get("autonomous_ai_engine_claim_ready")
                ),
                "autonomous_ai_engine_claim_blockers": _as_list(
                    commercial_gap_ledger_status.get("autonomous_ai_engine_claim_blockers")
                ),
                "full_gap_ledger_ready": bool(
                    commercial_gap_ledger_status.get("full_gap_ledger_ready")
                ),
                "summary": _as_dict(commercial_gap_ledger_status.get("summary")),
                "ledger_split_summary": gap_ledger_split_summary,
                "blocker_count": len(_as_list(commercial_gap_ledger_status.get("blockers"))),
                "blockers": _as_list(commercial_gap_ledger_status.get("blockers")),
                "next_locally_closable_gaps": _as_list(
                    commercial_gap_ledger_status.get("next_locally_closable_gaps")
                ),
                "ready": bool(commercial_gap_ledger_status.get("full_gap_ledger_ready")),
            },
            "gap_ledger_evidence_audit": {
                "status": str(gap_ledger_evidence_audit.get("status", "missing")),
                "contract_pass": bool(gap_ledger_evidence_audit.get("contract_pass")),
                "ledger_status": str(gap_ledger_evidence_audit.get("ledger_status", "")),
                "full_gap_ledger_ready": bool(
                    gap_ledger_evidence_audit.get("full_gap_ledger_ready")
                ),
                "row_count": _as_int(gap_ledger_evidence_audit.get("row_count"), 0),
                "closed_row_count": _as_int(
                    gap_ledger_evidence_audit.get("closed_row_count"), 0
                ),
                "nonclosed_row_count": _as_int(
                    gap_ledger_evidence_audit.get("nonclosed_row_count"), 0
                ),
                "ledger_split_summary": gap_ledger_audit_split_summary,
                "blocker_count": len(_as_list(gap_ledger_evidence_audit.get("blockers"))),
                "blockers": _as_list(gap_ledger_evidence_audit.get("blockers")),
                "claim_boundary": str(gap_ledger_evidence_audit.get("claim_boundary", "")),
                "ready": bool(gap_ledger_evidence_audit.get("contract_pass")),
            },
            "phase1_core_api_contract": _phase1_core_api_summary(phase1_core_api),
            "developer_preview_readiness": {
                "status": str(developer_preview.get("status", "missing")),
                "developer_preview_ready": bool(developer_preview.get("developer_preview_ready")),
                "blocker_count": _as_int(developer_preview.get("blocker_count"), 0),
                "future_commercial_blocker_count": _as_int(
                    developer_preview.get("future_commercial_blocker_count"), 0
                ),
                "category_counts": {
                    key: _as_int(_as_dict(value).get("blocker_count"), 0)
                    for key, value in _as_dict(developer_preview.get("categories")).items()
                },
                "freeze_policy": _as_dict(_as_dict(developer_preview.get("scope")).get("freeze_policy")),
                "gap_ledger_closure_requirement_visibility": (
                    _developer_preview_closure_visibility_summary(developer_preview)
                ),
                "scope_boundary_sync_summary": (
                    _developer_preview_scope_boundary_summary(developer_preview)
                ),
                "claim_boundary": str(developer_preview.get("claim_boundary", "")),
                "ready": bool(developer_preview.get("developer_preview_ready")),
            },
            "developer_preview_rc": {
                "status": str(developer_preview_rc.get("status", "missing")),
                "contract_pass": bool(developer_preview_rc.get("contract_pass")),
                "deliverable_count": _as_int(developer_preview_rc.get("deliverable_count"), 0),
                "deliverable_pass_count": _as_int(
                    developer_preview_rc.get("deliverable_pass_count"), 0
                ),
                "final_gate_count": _as_int(developer_preview_rc.get("final_gate_count"), 0),
                "final_gate_pass_count": _as_int(
                    developer_preview_rc.get("final_gate_pass_count"), 0
                ),
                "blocker_count": len(_as_list(developer_preview_rc.get("blockers"))),
                "blockers": _as_list(developer_preview_rc.get("blockers")),
                "claim_boundary": str(developer_preview_rc.get("claim_boundary", "")),
                "ready": bool(developer_preview_rc.get("contract_pass")),
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
                "blocker_grouping_metadata": (
                    fresh.get("blocker_grouping_metadata")
                    if isinstance(fresh.get("blocker_grouping_metadata"), dict)
                    else {}
                ),
                "lane_boundary_metadata": (
                    fresh.get("lane_boundary_metadata")
                    if isinstance(fresh.get("lane_boundary_metadata"), dict)
                    else {}
                ),
            },
            "customer_shadow": {
                "contract_pass": bool(customer.get("contract_pass")),
                "completed_shadow_case_count": completed_shadow_cases,
                "min_completed_shadow_cases": min_shadow_cases,
                "evidence_row_count": len(customer_rows),
                "completed_evidence_row_count": completed_customer_rows,
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
                "blocker_count": len(ux_blockers),
                "blockers": ux_blockers,
                "top_level_blockers": [
                    f"human_ux::{item}" for item in ux_top_level_blockers
                ],
                "suppressed_detail_blocker_count": len(ux_suppressed_detail_blockers),
                "suppressed_detail_blockers": [
                    f"human_ux::{item}" for item in ux_suppressed_detail_blockers
                ],
                "detail_blocker_represented_by": {
                    f"human_ux::{item}": "human_ux::observation_file_missing"
                    for item in ux_suppressed_detail_blockers
                },
                "checks": _as_dict(ux_new_user.get("checks")),
                "summary": ux_summary,
                "ready": ux_human_ready,
            },
            "license_status": {
                "contract_pass": bool(license_status.get("contract_pass")),
                "status": str(_as_dict(license_status.get("summary")).get("status", "")),
                "ready": license_ready,
            },
            "paid_pilot_scope_guard": {
                "contract_pass": bool(scope_guard.get("contract_pass")),
                "ready": supported_scope_guard_ready,
                "checks": scope_guard_checks,
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
                "top_level_blockers": g1_root_blockers,
                "suppressed_detail_blocker_count": len(g1_suppressed_detail_blockers),
                "suppressed_detail_blockers": g1_suppressed_detail_blockers,
                "detail_blocker_represented_by": {
                    item: "g1::*" for item in g1_suppressed_detail_blockers
                },
                "blocker_grouping_metadata": _g1_blocker_grouping_metadata(
                    top_level_blockers=g1_root_blockers,
                    suppressed_detail_blockers=g1_suppressed_detail_blockers,
                ),
                "closure_boundary_metadata": _g1_closure_boundary_metadata(
                    g1_full_mesh_ready=g1_full_mesh_ready,
                    g1_full_load_lane_ready=g1_full_load_lane_ready,
                    g1_lane_child_gate_ready=g1_lane_child_gate_ready,
                    g1_lane_hip_consistency_proof=g1_lane_hip_consistency_proof,
                ),
                "full_load_hip_newton_lane_ready": g1_full_load_lane_ready,
                "full_load_hip_newton_lane_status": str(
                    g1_full_load_lane.get("status", "")
                ),
                "full_load_hip_newton_lane_reused_evidence": g1_full_load_lane.get("reused_evidence"),
                "full_load_hip_newton_lane_full_load_input_pass": g1_lane_full_load_input_pass,
                "full_load_hip_newton_lane_observed_load_scale": g1_lane_observed_load,
                "full_load_hip_newton_lane_required_load_scale": g1_lane_required_load,
                "full_load_hip_newton_frontier_non_promoting_evidence": (
                    g1_full_load_lane.get("frontier_non_promoting_evidence")
                    if isinstance(
                        g1_full_load_lane.get("frontier_non_promoting_evidence"),
                        dict,
                    )
                    else {}
                ),
                "full_load_hip_newton_child_hip_residual_refresh_ready": (
                    g1_lane_child_hip_refresh_ready
                ),
                "full_load_hip_newton_child_hip_residual_refresh": (
                    g1_lane_child_hip_refresh
                ),
                "full_load_hip_newton_child_gate_ready": (
                    g1_lane_child_gate_ready
                ),
                "full_load_hip_newton_child_gate": g1_lane_child_gate,
                "full_load_hip_newton_hip_consistency_proof_ready": (
                    bool(g1_lane_hip_consistency_proof["ready"])
                ),
                "full_load_hip_newton_hip_consistency_proof": (
                    g1_lane_hip_consistency_proof
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
            "assisted_service_pilot": {
                "ready": assisted_service_pilot_ready,
                "blocker_count": len(assisted_service_pilot_blockers),
                "blockers": assisted_service_pilot_blockers,
                "snapshot_source_state_consistent": snapshot_source_state_consistent,
                "workstation_delivery_8_of_8": workstation_summary["workstation_delivery_8_of_8"],
                "supported_scope_guard_ready": supported_scope_guard_ready,
                "full_quality_ready": full_quality_ready,
                "github_sync_clean": github_sync_clean,
                "human_ux_observation_ready": ux_human_ready,
                "license_approval_ready": license_ready,
                "acceptance_package_ready": workstation_summary["acceptance_package_ready"],
                "engineer_review_boundary_ready": workstation_summary[
                    "engineer_review_boundary_ready"
                ],
                "claim_boundary": workstation_summary["claim_boundary"],
            },
            "solver_product": {
                "ready": solver_product_pilot_ready,
                "blocker_count": len(solver_product_blockers),
                "blockers": solver_product_blockers,
                "snapshot_source_state_consistent": snapshot_source_state_consistent,
                "independent_product_ready": independent_product_ready,
                "g1_full_mesh_full_load_ready": g1_full_mesh_ready,
                "g1_full_load_hip_newton_lane_ready": g1_full_load_lane_ready,
                "external_benchmark_4_of_4_ready": external_benchmark_ready,
                "customer_shadow_3_of_3_ready": customer_ready,
                "fresh_validation_8_of_8_ready": fresh_ready,
            },
            "release_control_cleanup": release_control_cleanup_component,
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
                "phase3_release_control_cleanup_plan": {
                    "path": str(paths.phase3_release_control_cleanup_plan),
                    "status": phase3_release_control_cleanup_plan.get("status", "missing"),
                    "contract_pass": bool(phase3_release_control_cleanup_plan.get("contract_pass")),
                    "candidate_set_source": phase3_release_control_cleanup_plan.get(
                        "candidate_set_source", ""
                    ),
                    "candidate_set_scope": phase3_release_control_cleanup_plan.get(
                        "candidate_set_scope", ""
                    ),
                    "current_worktree_diagnostics_included": bool(
                        phase3_release_control_cleanup_plan.get(
                            "current_worktree_diagnostics_included"
                        )
                    ),
                    "current_worktree_diagnostic_source": phase3_release_control_cleanup_plan.get(
                        "current_worktree_diagnostic_source", ""
                    ),
                    "candidate_release_control_commit_set_count": phase3_release_control_cleanup_plan.get(
                        "candidate_release_control_commit_set_count",
                        0,
                    ),
                    "path_role_counts": phase3_release_control_cleanup_plan.get("path_role_counts", {}),
                    "recommended_action_counts": phase3_release_control_cleanup_plan.get(
                        "recommended_action_counts",
                        {},
                    ),
                    "track_or_add_required_path_count": len(
                        _as_list(
                            phase3_release_control_cleanup_plan.get(
                                "track_or_add_required_paths"
                            )
                        )
                    ),
                    "resolve_or_commit_dirty_tracked_path_count": len(
                        _as_list(
                            phase3_release_control_cleanup_plan.get(
                                "resolve_or_commit_dirty_tracked_paths"
                            )
                        )
                    ),
                    "human_git_action_required": bool(
                        phase3_release_control_cleanup_plan.get("human_git_action_required")
                    ),
                    "codex_commit_or_push_performed": bool(
                        phase3_release_control_cleanup_plan.get("codex_commit_or_push_performed")
                    ),
                    "human_handoff_status": phase3_cleanup_handoff.get("status", ""),
                    "human_handoff_next_action": phase3_cleanup_handoff.get("next_action", ""),
                    "human_handoff_suggested_command_count": len(
                        _as_list(phase3_cleanup_handoff.get("suggested_local_command_args"))
                    ),
                    "human_handoff_push_or_release_command_included": bool(
                        phase3_cleanup_handoff.get("push_or_release_command_included")
                    ),
                    "claim_boundary": phase3_release_control_cleanup_plan.get("claim_boundary", ""),
                },
            },
        },
        "artifacts": {
            field: str(getattr(paths, field))
            for field in paths.__dataclass_fields__
        },
    }


def _strip_volatile_for_compare(
    payload: Any,
    path: tuple[str, ...] = (),
) -> Any:
    """Return ``payload`` with non-semantic snapshot wrapper fields removed.

    The top-level source commit records the repository point used to generate
    the checked-in snapshot. Committing the snapshot necessarily advances HEAD,
    so freshness is enforced through the metadata source-state rows and blocker
    set rather than by requiring that wrapper field to equal the current commit.
    Nested source_commit_sha and freshness verdicts remain semantic. Metadata
    rows also include commit-boundary diagnostics that legitimately change
    when a receipt-only snapshot refresh is checked in, so those diagnostics
    are excluded from consistency comparison while the underlying freshness
    verdict is still enforced.
    """
    if isinstance(payload, dict):
        worktree_diagnostic_path = path == ("state_consistency", "worktree")
        metadata_row_path = (
            len(path) == 2
            and path[0] == "state_consistency"
            and path[1] == "metadata_rows"
        )
        return {
            key: _strip_volatile_for_compare(value, (*path, key))
            for key, value in payload.items()
            if key != "generated_at"
            and not (path == () and key == "source_commit_sha")
            and not (worktree_diagnostic_path and key in {"status_rows", "dirty_paths"})
            and not (
                metadata_row_path
                and key
                in {
                    "changed_paths_since_source_commit",
                    "source_commit_matches_head",
                    "source_state_kind",
                }
            )
        }
    if isinstance(payload, list):
        return [_strip_volatile_for_compare(item, path) for item in payload]
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

    Volatile ``generated_at`` fields and the top-level ``source_commit_sha``
    wrapper are ignored. Nested source commits, status, evidence freshness,
    blockers, and component flags must match.

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
        additional_receipt_paths=(out_path,),
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
        "--no-write",
        action="store_true",
        help=(
            "Build and print the snapshot without writing --out. Use this for "
            "inspection so protected evidence files are not refreshed accidentally."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Non-mutating: compare the existing --out file with a freshly generated "
            "snapshot (ignoring generated_at and the top-level source_commit_sha "
            "wrapper) and exit non-zero if the stored snapshot is missing, unreadable, "
            "or semantically different. When combined with --fail-blocked, the "
            "matched snapshot must also be release-ready."
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
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not args.no_write:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text if args.json else f"Product readiness snapshot: {payload['status']}", end="" if args.json else "\n")
    return 1 if args.fail_blocked and not payload["release_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
