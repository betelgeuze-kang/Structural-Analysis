#!/usr/bin/env python3
"""Run the strict G1 full-load HIP Newton lane without promoting diagnostics."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import input_checksums  # noqa: E402


SCHEMA_VERSION = "g1-full-load-hip-newton-lane.v1"
ROOT = Path(__file__).resolve().parent.parent
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_CHECKPOINT = (
    PRODUCTIZATION
    / "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4_children"
    / "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4_candidate1_target4_support4_final_checkpoint.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
DEFAULT_CHILD_OUT = PRODUCTIZATION / "g1_full_load_hip_newton_direct_probe.json"
DEFAULT_HIP_CONSISTENCY_PROOF = (
    PRODUCTIZATION / "mgt_residual_jacobian_consistency_hip_required_probe.json"
)
DIRECT_PROBE = Path("implementation/phase1/run_mgt_direct_residual_newton_probe.py")
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
HIP_RESIDUAL_REPLAY_BACKENDS = {
    "hip_full_residual",
    "hip_full_residual_resident",
    "rust_hip_full_residual_ffi",
}
HIP_CHILD_RESIDUAL_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("matrix_free_global_krylov", "child_global_krylov"),
    (
        "current_tangent_residual_row_correction",
        "child_current_tangent_residual_row",
    ),
)
CHECKPOINT_EVIDENCE_SOURCES: tuple[Path, ...] = (
    PRODUCTIZATION / "g1_checkpoint_retention_manifest.json",
    PRODUCTIZATION / "mgt_g1_followup387_shell_material_budgeted_continuation_status.json",
)
NPZ_PATH_KEYS: tuple[str, ...] = (
    "compact_checkpoint",
    "latest_frontier_compact_checkpoint",
    "retained_checkpoint",
    "retained_checkpoint_npz",
    "retained_checkpoint_at_time",
    "checkpoint_path",
    "checkpoint_npz",
)
LOAD_PATH_PROVENANCE_KEYS: tuple[str, ...] = (
    "load_scale",
    "max_converged_load_scale",
    "frontier_load_scale",
    "latest_frontier_load_scale",
    "accepted_frontier_load_scale",
    "first_failed_load_scale",
    "first_direct_failed_load_scale",
    "next_failed_load_scale_after_frontier",
    "required_load_scale",
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _git_rev_parse(ref: str) -> str:
    if not ref:
        return ""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", ref],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _git_diff_name_only(base: str, head: str) -> list[str]:
    if not base or not head:
        return []
    try:
        output = subprocess.check_output(
            ["git", "diff", "--name-only", base, head],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _receipt_commit_allowed_path(path: str) -> bool:
    if path in {"README.md", "docs/commercialization-gap-current-state.md"}:
        return True
    if path.startswith("docs/ai/dispatch/") and path.endswith(".md"):
        return True
    if path.startswith("implementation/phase1/release_evidence/productization/"):
        return path.endswith((".json", ".md"))
    if path.startswith("implementation/phase1/release_evidence/surface/"):
        return path.endswith(".json")
    if path in {
        "implementation/phase1/customer_shadow_evidence_status.json",
        "implementation/phase1/support_bundle_manifest.json",
        "implementation/phase1/workstation_delivery_readiness.json",
        "implementation/phase1/release/independent_product_readiness.json",
        "implementation/phase1/release/external_benchmark_submission_readiness.json",
    }:
        return True
    return False


def _g1_hip_freshness_relevant_path(path: str) -> bool:
    relevant_exact_paths = {
        "implementation/phase1/run_mgt_direct_residual_newton_probe.py",
    }
    if path in relevant_exact_paths:
        return True
    status_builder_paths = {
        "scripts/build_g1_f2g_f2h_cause_narrowing_status.py",
        "scripts/build_g1_global_connectivity_load_path_audit.py",
        "scripts/build_g1_support_elastic_link_reconciliation_audit.py",
    }
    if path in status_builder_paths:
        return False
    unrelated_prefixes = (
        "src/structural_analysis/benchmark/",
    )
    if path.startswith(unrelated_prefixes):
        return False
    relevant_prefixes = (
        "implementation/phase1/src/",
        "src/structural_analysis/",
        "scripts/build_g1_",
        "scripts/build_mgt_",
        "scripts/run_mgt_",
    )
    return path.startswith(relevant_prefixes)


def _source_state_freshness(
    *, proof_source_commit: str, lane_source_commit_sha: str
) -> tuple[bool, str, list[str]]:
    if not proof_source_commit:
        return False, "missing_source_commit", []
    if not lane_source_commit_sha or proof_source_commit == lane_source_commit_sha:
        return True, "exact", []
    proof_source = _git_rev_parse(proof_source_commit)
    lane_source = _git_rev_parse(lane_source_commit_sha)
    if not proof_source or not lane_source:
        return False, "unresolved_source_commit", []
    changed_paths = _git_diff_name_only(proof_source, lane_source)
    non_receipt_paths = [
        path for path in changed_paths if not _receipt_commit_allowed_path(path)
    ]
    if non_receipt_paths:
        relevant_paths = [
            path for path in non_receipt_paths if _g1_hip_freshness_relevant_path(path)
        ]
        if relevant_paths:
            return False, "g1_hip_paths_changed", relevant_paths
        return True, "non_g1_hip_paths_changed", non_receipt_paths
    return True, "receipt_only_commit", changed_paths


def _read_optional_float(archive: Any, key: str) -> float | None:
    if key not in archive.files:
        return None
    raw = archive[key]
    try:
        value = float(np.asarray(raw).item())
    except (TypeError, ValueError):
        return None
    if value != value:
        return None
    return value


def _read_failed_bracket_load_scales(archive: Any) -> list[float]:
    candidates = (
        "failed_bracket_load_scales",
        "failed_brackets_load_scales",
    )
    for key in candidates:
        if key not in archive.files:
            continue
        raw = np.asarray(archive[key])
        if raw.ndim == 0:
            try:
                value = float(raw.item())
            except (TypeError, ValueError):
                continue
            return [value]
        values: list[float] = []
        for entry in raw.reshape(-1):
            try:
                values.append(float(entry))
            except (TypeError, ValueError):
                continue
        return values
    return []


def _load_checkpoint_meta(path: Path) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    if not path.exists():
        return {"path": str(path), "load_scale": None}, ["checkpoint_missing"]
    try:
        with np.load(path, allow_pickle=False) as archive:
            load_scale = (
                float(np.asarray(archive["load_scale"]).item())
                if "load_scale" in archive.files
                else None
            )
            dof_count = (
                int(np.asarray(archive["displacement_u"]).size)
                if "displacement_u" in archive.files
                else None
            )
            schema = (
                str(np.asarray(archive["checkpoint_schema"]).item())
                if "checkpoint_schema" in archive.files
                else ""
            )
            frontier_load_scale = _read_optional_float(archive, "frontier_load_scale")
            failed_bracket_load_scales = _read_failed_bracket_load_scales(archive)
    except Exception as exc:
        return {
            "path": str(path),
            "load_scale": None,
            "error": exc.__class__.__name__,
        }, ["checkpoint_unreadable"]
    if load_scale is None:
        blockers.append("checkpoint_load_scale_missing")
    return {
        "path": str(path),
        "schema": schema,
        "load_scale": load_scale,
        "dof_count": dof_count,
        "frontier_load_scale": frontier_load_scale,
        "failed_bracket_load_scales": failed_bracket_load_scales,
        "load_path_provenance_present": bool(
            frontier_load_scale is not None or failed_bracket_load_scales
        ),
    }, blockers


def _load_path_provenance_blockers(
    *,
    checkpoint_meta: dict[str, Any],
    required_load_scale: float,
    full_load_tolerance: float,
) -> list[str]:
    """Return explicit load-path provenance blockers.

    The numeric ``load_scale`` gate is not enough. When a checkpoint claims
    ``load_scale >= required_load_scale`` but the metadata shows an accepted
    frontier below the required full load or a failed bracket below full load,
    the lane must be blocked even though the numeric claim is satisfied.
    """
    if not checkpoint_meta.get("load_path_provenance_present"):
        return []
    observed_load_scale = checkpoint_meta.get("load_scale")
    if observed_load_scale is None:
        return []
    try:
        observed_load_value = float(observed_load_scale)
    except (TypeError, ValueError):
        return []
    threshold = float(required_load_scale) - float(full_load_tolerance)
    if observed_load_value < threshold:
        return []
    blockers: list[str] = []
    frontier_load_scale = checkpoint_meta.get("frontier_load_scale")
    if isinstance(frontier_load_scale, (int, float)):
        if float(frontier_load_scale) < threshold:
            blockers.append(
                "load_path_provenance_accepted_frontier_below_full_load"
            )
    failed_bracket_load_scales_raw = checkpoint_meta.get("failed_bracket_load_scales")
    failed_bracket_below_full_load: list[float] = []
    if isinstance(failed_bracket_load_scales_raw, list):
        for entry in failed_bracket_load_scales_raw:
            try:
                value = float(entry)
            except (TypeError, ValueError):
                continue
            if value < threshold:
                failed_bracket_below_full_load.append(value)
    if failed_bracket_below_full_load:
        blockers.append("load_path_provenance_failed_bracket_below_full_load")
    return blockers


def _normalize_workspace_path(value: object) -> Path | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or not stripped.lower().endswith(".npz"):
        return None
    candidate = Path(stripped)
    if candidate.is_absolute():
        return candidate
    return candidate


def _collect_npz_paths_from_json(payload: object) -> list[Path]:
    found: list[Path] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in NPZ_PATH_KEYS and isinstance(value, str):
                resolved = _normalize_workspace_path(value)
                if resolved is not None:
                    found.append(resolved)
                continue
            if isinstance(value, dict):
                inner_path = value.get("path")
                if isinstance(inner_path, str) and key in NPZ_PATH_KEYS:
                    resolved = _normalize_workspace_path(inner_path)
                    if resolved is not None:
                        found.append(resolved)
            found.extend(_collect_npz_paths_from_json(value))
    elif isinstance(payload, list):
        for entry in payload:
            found.extend(_collect_npz_paths_from_json(entry))
    return found


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _checkpoint_provenance_context(payload: object) -> dict[str, float]:
    if not isinstance(payload, dict):
        return {}
    context: dict[str, float] = {}
    for key in LOAD_PATH_PROVENANCE_KEYS:
        value = _float_or_none(payload.get(key))
        if value is not None:
            context[key] = value
    return context


def _collect_npz_records_from_json(payload: object) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        context = _checkpoint_provenance_context(payload)
        for key, value in payload.items():
            if key in NPZ_PATH_KEYS and isinstance(value, str):
                resolved = _normalize_workspace_path(value)
                if resolved is not None:
                    found.append({"path": resolved, "provenance_context": context})
                continue
            if isinstance(value, dict):
                inner_path = value.get("path")
                if isinstance(inner_path, str) and key in NPZ_PATH_KEYS:
                    resolved = _normalize_workspace_path(inner_path)
                    if resolved is not None:
                        found.append({"path": resolved, "provenance_context": context})
            found.extend(_collect_npz_records_from_json(value))
    elif isinstance(payload, list):
        for entry in payload:
            found.extend(_collect_npz_records_from_json(entry))
    return found


def _scan_evidence_checkpoint_paths(
    sources: tuple[Path, ...] = CHECKPOINT_EVIDENCE_SOURCES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    per_source: list[dict[str, Any]] = []
    for source in sources:
        entry: dict[str, Any] = {
            "path": str(source),
            "available": False,
            "candidate_count": 0,
            "candidate_paths_sample": [],
        }
        if not source.exists():
            per_source.append(entry)
            continue
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception as exc:
            entry["error"] = exc.__class__.__name__
            per_source.append(entry)
            continue
        entry["available"] = True
        records: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for record in _collect_npz_records_from_json(payload):
            path = record["path"]
            path_key = str(path)
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            records.append(record)
        existing_paths = {str(record["path"]) for record in candidates}
        for record in records:
            if str(record["path"]) not in existing_paths:
                candidates.append(record)
                existing_paths.add(str(record["path"]))
        entry["candidate_count"] = len(records)
        entry["candidate_paths_sample"] = [str(record["path"]) for record in records[:12]]
        per_source.append(entry)
    return candidates, per_source


def _auto_select_checkpoint(
    *,
    required_load_scale: float,
    full_load_tolerance: float,
    sources: tuple[Path, ...] = CHECKPOINT_EVIDENCE_SOURCES,
) -> dict[str, Any]:
    candidates, per_source = _scan_evidence_checkpoint_paths(sources)
    observed: list[dict[str, Any]] = []
    for index, record in enumerate(candidates):
        path = record["path"]
        meta, _blockers = _load_checkpoint_meta(path)
        entry = {
            "path": str(path),
            "candidate_index": index,
            "exists": path.exists(),
            "load_scale": meta.get("load_scale"),
            "schema": meta.get("schema", ""),
            "dof_count": meta.get("dof_count"),
            "provenance_context": record.get("provenance_context", {}),
        }
        observed.append(entry)
    loadable = [
        entry
        for entry in observed
        if entry["exists"] and isinstance(entry["load_scale"], (int, float))
    ]
    if not loadable:
        return {
            "mode": "auto_select",
            "sources": per_source,
            "candidate_count": len(candidates),
            "loadable_count": 0,
            "unloadable_count": len(observed),
            "highest_observed_load_scale": None,
            "loadable_candidates": [],
            "selected_checkpoint": None,
            "selection_reason": "no_loadable_candidates",
        }
    ranked = sorted(
        loadable,
        key=lambda e: (float(e["load_scale"]), int(e["candidate_index"])),
        reverse=True,
    )
    best = ranked[0]
    best_load = float(best["load_scale"])
    meets_full_load = best_load >= float(required_load_scale) - float(full_load_tolerance)
    reason = (
        "full_load_candidate_selected"
        if meets_full_load
        else "highest_sub_full_load_candidate_selected"
    )
    return {
        "mode": "auto_select",
        "sources": per_source,
        "candidate_count": len(candidates),
        "loadable_count": len(loadable),
        "unloadable_count": len(observed) - len(loadable),
        "highest_observed_load_scale": best_load,
        "loadable_candidates": ranked[:12],
        "selected_checkpoint": {
            "path": str(best["path"]),
            "load_scale": best_load,
            "meets_full_load": meets_full_load,
            "schema": best.get("schema", ""),
            "dof_count": best.get("dof_count"),
            "provenance_context": best.get("provenance_context", {}),
        },
        "selection_reason": reason,
    }


def _load_path_provenance_assessment(
    *,
    checkpoint_resolution: dict[str, Any],
    required_load_scale: float,
    full_load_tolerance: float,
) -> tuple[dict[str, Any], list[str]]:
    selection = checkpoint_resolution.get("selection")
    selected = selection.get("selected_checkpoint") if isinstance(selection, dict) else None
    selected = selected if isinstance(selected, dict) else {}
    context = selected.get("provenance_context")
    context = context if isinstance(context, dict) else {}
    blockers: list[str] = []
    below_required: dict[str, float] = {}
    for key in (
        "load_scale",
        "max_converged_load_scale",
        "frontier_load_scale",
        "latest_frontier_load_scale",
        "accepted_frontier_load_scale",
    ):
        value = _float_or_none(context.get(key))
        if value is not None and value < float(required_load_scale) - float(full_load_tolerance):
            below_required[key] = value
    for key in (
        "first_failed_load_scale",
        "first_direct_failed_load_scale",
        "next_failed_load_scale_after_frontier",
    ):
        value = _float_or_none(context.get(key))
        if value is not None and value <= float(required_load_scale) + float(full_load_tolerance):
            below_required[key] = value
    if below_required:
        blockers.append("checkpoint_load_path_provenance_below_required_full_load")
    return {
        "context": context,
        "required_load_scale": float(required_load_scale),
        "provenance_below_required_full_load": below_required,
        "passed": not below_required,
    }, blockers


def _resolve_checkpoint(
    *,
    requested: Path | None,
    required_load_scale: float,
    full_load_tolerance: float,
    sources: tuple[Path, ...] = CHECKPOINT_EVIDENCE_SOURCES,
) -> tuple[Path | None, dict[str, Any]]:
    if requested is None:
        selection = _auto_select_checkpoint(
            required_load_scale=required_load_scale,
            full_load_tolerance=full_load_tolerance,
            sources=sources,
        )
        selected = selection.get("selected_checkpoint") or {}
        selected_path = selected.get("path")
        if not selected_path:
            return None, {
                "requested_path": None,
                "mode": "auto_select",
                "selection": selection,
            }
        return Path(selected_path), {
            "requested_path": None,
            "mode": "auto_select",
            "selection": selection,
        }
    return requested, {
        "requested_path": str(requested),
        "mode": "explicit",
        "selection": None,
    }


def _checkpoint_resolution_gate(
    *,
    checkpoint_resolution: dict[str, Any],
    checkpoint_meta: dict[str, Any],
    required_load_scale: float,
    full_load_tolerance: float,
) -> tuple[dict[str, Any], list[str]]:
    selection = checkpoint_resolution.get("selection")
    selection = selection if isinstance(selection, dict) else {}
    threshold = float(required_load_scale) - float(full_load_tolerance)
    if checkpoint_resolution.get("mode") == "explicit":
        selected_load = _float_or_none(checkpoint_meta.get("load_scale"))
        full_load_candidate_count = int(
            selected_load is not None and selected_load >= threshold
        )
        candidate_count = 1 if checkpoint_meta.get("path") else 0
        loadable_count = 1 if selected_load is not None else 0
        unloadable_count = candidate_count - loadable_count
        highest_observed = selected_load
        selected_checkpoint_load_scale = selected_load
        selected_checkpoint_meets_full_load = bool(full_load_candidate_count)
    else:
        loadable_candidates = selection.get("loadable_candidates")
        loadable_candidates = (
            loadable_candidates if isinstance(loadable_candidates, list) else []
        )
        full_load_candidates: list[dict[str, Any]] = []
        for candidate in loadable_candidates:
            if not isinstance(candidate, dict):
                continue
            candidate_load = _float_or_none(candidate.get("load_scale"))
            if candidate_load is None or candidate_load < threshold:
                continue
            full_load_candidates.append(candidate)
        highest_observed = _float_or_none(selection.get("highest_observed_load_scale"))
        selected = selection.get("selected_checkpoint")
        selected = selected if isinstance(selected, dict) else {}
        full_load_candidate_count = len(full_load_candidates)
        candidate_count = selection.get("candidate_count")
        loadable_count = selection.get("loadable_count")
        unloadable_count = selection.get("unloadable_count")
        selected_checkpoint_load_scale = _float_or_none(selected.get("load_scale"))
        selected_checkpoint_meets_full_load = bool(
            selected.get("meets_full_load") is True
        )
    blockers: list[str] = []
    if full_load_candidate_count == 0:
        blockers.append("checkpoint_resolution_no_full_load_candidate")
    return {
        "schema_version": "g1-checkpoint-resolution-gate.v1",
        "mode": checkpoint_resolution.get("mode"),
        "required_load_scale": float(required_load_scale),
        "full_load_tolerance": float(full_load_tolerance),
        "candidate_count": candidate_count,
        "loadable_count": loadable_count,
        "unloadable_count": unloadable_count,
        "highest_observed_load_scale": highest_observed,
        "full_load_candidate_count": full_load_candidate_count,
        "selected_checkpoint_load_scale": selected_checkpoint_load_scale,
        "selected_checkpoint_meets_full_load": selected_checkpoint_meets_full_load,
        "highest_observed_gap_to_required_load_scale": (
            float(required_load_scale) - highest_observed
            if highest_observed is not None
            else None
        ),
        "passed": bool(full_load_candidate_count),
        "blockers": blockers,
        "claim_boundary": (
            "This gate proves only whether the scanned checkpoint evidence contains "
            "a loadable checkpoint at the required full-load scale. It does not "
            "prove residual, increment, material Newton, or production ROCm/HIP "
            "closure."
        ),
    }, blockers


def _workspace_checkpoint_inventory(
    *,
    scan_root: Path | None,
    required_load_scale: float,
    full_load_tolerance: float,
    sample_limit: int = 12,
) -> dict[str, Any]:
    if scan_root is None:
        return {
            "schema_version": "g1-workspace-checkpoint-inventory.v1",
            "enabled": False,
            "scan_root": None,
            "candidate_count": 0,
            "loadable_count": 0,
            "full_load_candidate_count": 0,
            "highest_observed_load_scale": None,
            "highest_observed_gap_to_required_load_scale": None,
            "top_loadable_candidates": [],
            "claim_boundary": (
                "Workspace checkpoint inventory was not requested for this in-process "
                "build_lane_report call."
            ),
        }
    root = scan_root if scan_root.is_absolute() else ROOT / scan_root
    if not root.exists():
        return {
            "schema_version": "g1-workspace-checkpoint-inventory.v1",
            "enabled": True,
            "scan_root": str(scan_root),
            "scan_root_exists": False,
            "candidate_count": 0,
            "loadable_count": 0,
            "full_load_candidate_count": 0,
            "highest_observed_load_scale": None,
            "highest_observed_gap_to_required_load_scale": None,
            "top_loadable_candidates": [],
            "claim_boundary": (
                "The requested workspace checkpoint scan root does not exist; no "
                "full-load checkpoint can be inferred from this inventory."
            ),
        }
    observed: list[dict[str, Any]] = []
    candidate_count = 0
    for path in sorted(root.rglob("*.npz")):
        candidate_count += 1
        try:
            rel_path = path.relative_to(ROOT)
        except ValueError:
            rel_path = path
        meta, blockers = _load_checkpoint_meta(path)
        load_scale = _float_or_none(meta.get("load_scale"))
        if load_scale is None:
            continue
        observed.append(
            {
                "path": str(rel_path),
                "load_scale": load_scale,
                "schema": meta.get("schema", ""),
                "dof_count": meta.get("dof_count"),
                "blockers": blockers,
            }
        )
    threshold = float(required_load_scale) - float(full_load_tolerance)
    observed.sort(key=lambda row: float(row["load_scale"]), reverse=True)
    full_load_candidates = [
        row for row in observed if float(row["load_scale"]) >= threshold
    ]
    highest = float(observed[0]["load_scale"]) if observed else None
    return {
        "schema_version": "g1-workspace-checkpoint-inventory.v1",
        "enabled": True,
        "scan_root": str(scan_root),
        "scan_root_exists": True,
        "candidate_count": candidate_count,
        "loadable_count": len(observed),
        "full_load_candidate_count": len(full_load_candidates),
        "highest_observed_load_scale": highest,
        "highest_observed_gap_to_required_load_scale": (
            float(required_load_scale) - highest if highest is not None else None
        ),
        "top_loadable_candidates": observed[:sample_limit],
        "claim_boundary": (
            "This inventory scans local productization NPZ checkpoints for load-scale "
            "metadata. It can prove that no local full-load candidate is visible in "
            "the scanned workspace, but it does not prove residual, increment, "
            "material Newton, HIP residency, or G1 closure."
        ),
    }


def _g1_lane_blocker_partition(
    *,
    checkpoint_resolution_gate: dict[str, Any],
    load_path_provenance: dict[str, Any],
    load_path_provenance_blockers: list[str],
    hip_consistency_proof: dict[str, Any],
    child_gate_evidence: dict[str, Any],
    child_hip_residual_refresh_evidence: dict[str, Any],
) -> dict[str, Any]:
    worker = hip_consistency_proof.get("production_rocm_hip_residual_jvp_worker")
    worker = worker if isinstance(worker, dict) else {}
    return {
        "schema_version": "g1-full-load-hip-newton-blocker-partition.v1",
        "checkpoint_resolution": {
            "ready": checkpoint_resolution_gate.get("passed") is True,
            "blockers": _string_list(checkpoint_resolution_gate.get("blockers")),
            "required_load_scale": checkpoint_resolution_gate.get("required_load_scale"),
            "highest_observed_load_scale": checkpoint_resolution_gate.get(
                "highest_observed_load_scale"
            ),
            "highest_observed_gap_to_required_load_scale": (
                checkpoint_resolution_gate.get(
                    "highest_observed_gap_to_required_load_scale"
                )
            ),
            "full_load_candidate_count": checkpoint_resolution_gate.get(
                "full_load_candidate_count"
            ),
        },
        "load_path_provenance": {
            "ready": not load_path_provenance_blockers,
            "blockers": list(load_path_provenance_blockers),
            "provenance_below_required_full_load": load_path_provenance.get(
                "provenance_below_required_full_load"
            ),
        },
        "hip_consistency_proof": {
            "ready": bool(
                hip_consistency_proof.get("present") is True
                and hip_consistency_proof.get(
                    "consistent_residual_jacobian_newton_gate_passed"
                )
                is True
                and hip_consistency_proof.get("cpu_diagnostic_assembler_used") is False
                and hip_consistency_proof.get("production_hip_residual_jacobian_path")
                is True
                and not _string_list(hip_consistency_proof.get("receipt_blockers"))
            ),
            "source_state_fresh": hip_consistency_proof.get("source_state_fresh"),
            "receipt_blockers": _string_list(hip_consistency_proof.get("receipt_blockers")),
            "runtime_blockers": _string_list(hip_consistency_proof.get("runtime_blockers")),
        },
        "production_rocm_hip_residual_jvp_worker": {
            "ready": worker.get("ready") is True,
            "residual_jvp_worker_path_ready": worker.get(
                "residual_jvp_worker_path_ready"
            ),
            "g1_closure_gate_ready": worker.get("g1_closure_gate_ready"),
            "blockers": _string_list(worker.get("blockers")),
            "residual_jvp_worker_path_blockers": _string_list(
                worker.get("residual_jvp_worker_path_blockers")
            ),
            "g1_closure_gate_blockers": _string_list(
                worker.get("g1_closure_gate_blockers")
            ),
        },
        "child_direct_probe": {
            "ready": child_gate_evidence.get("ready") is True,
            "gate_blockers": _string_list(child_gate_evidence.get("blockers")),
            "hip_residual_refresh_ready": (
                child_hip_residual_refresh_evidence.get("ready") is True
            ),
            "hip_residual_refresh_blockers": _string_list(
                child_hip_residual_refresh_evidence.get("blockers")
            ),
        },
        "claim_boundary": (
            "This partition is diagnostic only. It separates checkpoint, load-path, "
            "HIP consistency, worker, and child-probe blockers without promoting "
            "G1 or full-load readiness."
        ),
    }


def _g1_lane_next_actions(
    *,
    checkpoint_resolution_gate: dict[str, Any],
    workspace_checkpoint_inventory: dict[str, Any] | None = None,
    hip_consistency_proof: dict[str, Any],
    child_gate_evidence: dict[str, Any],
    child_hip_residual_refresh_evidence: dict[str, Any],
    command: list[str],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if checkpoint_resolution_gate.get("passed") is not True:
        workspace_inventory = (
            workspace_checkpoint_inventory
            if isinstance(workspace_checkpoint_inventory, dict)
            else {}
        )
        action = {
            "id": "generate_full_load_1p0_checkpoint_candidate",
            "reason": "checkpoint_resolution_no_full_load_candidate",
            "required_load_scale": checkpoint_resolution_gate.get(
                "required_load_scale"
            ),
            "highest_observed_load_scale": checkpoint_resolution_gate.get(
                "highest_observed_load_scale"
            ),
            "highest_observed_gap_to_required_load_scale": (
                checkpoint_resolution_gate.get(
                    "highest_observed_gap_to_required_load_scale"
                )
            ),
            "acceptance_receipt": (
                "a loadable mgt-direct-residual-newton-state.v1 checkpoint with "
                "load_scale >= required_load_scale and no load-path provenance "
                "contradiction"
            ),
            "rerun_command": (
                "python3 scripts/run_g1_full_load_hip_newton_lane.py "
                "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
            ),
        }
        if workspace_inventory.get("enabled") is True:
            action.update(
                {
                    "workspace_scan_root": workspace_inventory.get("scan_root"),
                    "workspace_candidate_count": workspace_inventory.get(
                        "candidate_count"
                    ),
                    "workspace_full_load_candidate_count": (
                        workspace_inventory.get("full_load_candidate_count")
                    ),
                    "workspace_highest_observed_load_scale": (
                        workspace_inventory.get("highest_observed_load_scale")
                    ),
                    "workspace_highest_observed_gap_to_required_load_scale": (
                        workspace_inventory.get(
                            "highest_observed_gap_to_required_load_scale"
                        )
                    ),
                }
            )
        actions.append(
            action
        )
    worker = hip_consistency_proof.get("production_rocm_hip_residual_jvp_worker")
    worker = worker if isinstance(worker, dict) else {}
    if hip_consistency_proof.get("source_state_fresh") is False:
        actions.append(
            {
                "id": "refresh_hip_consistency_proof_for_current_head",
                "reason": "hip_consistency_proof_source_commit_sha_mismatch",
                "source_state_kind": hip_consistency_proof.get("source_state_kind"),
                "changed_paths_since_source_commit": hip_consistency_proof.get(
                    "changed_paths_since_source_commit"
                ),
            }
        )
    if (
        hip_consistency_proof.get("consistent_residual_jacobian_newton_gate_passed")
        is not True
    ):
        actions.append(
            {
                "id": "close_consistent_residual_jacobian_newton_gate",
                "reason": "hip_consistency_proof_gate_not_passed",
                "worker_id": worker.get("worker_id"),
                "worker_residual_jvp_path_ready": worker.get(
                    "residual_jvp_worker_path_ready"
                ),
                "worker_g1_closure_gate_ready": worker.get("g1_closure_gate_ready"),
                "receipt_blockers": _string_list(
                    hip_consistency_proof.get("receipt_blockers")
                ),
                "worker_g1_closure_gate_blockers": _string_list(
                    worker.get("g1_closure_gate_blockers")
                ),
            }
        )
    if (
        checkpoint_resolution_gate.get("passed") is True
        and hip_consistency_proof.get("consistent_residual_jacobian_newton_gate_passed")
        is True
        and (
            child_gate_evidence.get("ready") is not True
            or child_hip_residual_refresh_evidence.get("ready") is not True
        )
    ):
        actions.append(
            {
                "id": "run_full_load_child_direct_probe_with_hip_refresh",
                "reason": "child_direct_probe_evidence_missing_or_blocked",
                "command": command,
                "required_child_gate_blockers": _string_list(
                    child_gate_evidence.get("blockers")
                ),
                "required_hip_refresh_blockers": _string_list(
                    child_hip_residual_refresh_evidence.get("blockers")
                ),
            }
        )
    actions.append(
        {
            "id": "preserve_non_promoting_boundary_until_all_g1_receipts_pass",
            "reason": "g1_closure_requires_full_load_child_and_external_hip_proof",
            "promotes_g1_closure": False,
        }
    )
    return actions


def _dedupe_strings(rows: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for row in rows:
        if not isinstance(row, str) or not row or row in seen:
            continue
        seen.add(row)
        unique.append(row)
    return unique


def _g1_lane_terminal_requirement_breakdown(
    *,
    checkpoint_resolution_gate: dict[str, Any],
    load_path_provenance: dict[str, Any],
    load_path_provenance_blockers: list[str],
    hip_consistency_proof: dict[str, Any],
    hip_consistency_blockers: list[str],
    child_gate_evidence: dict[str, Any],
    child_hip_residual_refresh_evidence: dict[str, Any],
    command: list[str],
) -> dict[str, Any]:
    worker = hip_consistency_proof.get("production_rocm_hip_residual_jvp_worker")
    worker = worker if isinstance(worker, dict) else {}

    checkpoint_blockers = _dedupe_strings(
        [
            *_string_list(checkpoint_resolution_gate.get("blockers")),
            *load_path_provenance_blockers,
        ]
    )
    checkpoint_ready = bool(
        checkpoint_resolution_gate.get("passed") is True
        and not load_path_provenance_blockers
    )

    hip_proof_worker_prefixes = (
        "hip_consistency_proof_worker",
        "hip_consistency_proof_residual_jvp_worker",
        "hip_consistency_proof_production_rocm_hip_residual_jvp_worker",
    )
    hip_proof_blockers = _dedupe_strings(
        [
            blocker
            for blocker in hip_consistency_blockers
            if not blocker.startswith(hip_proof_worker_prefixes)
        ]
    )
    hip_proof_ready = bool(
        hip_consistency_proof.get("present") is True
        and hip_consistency_proof.get("source_state_fresh") is True
        and hip_consistency_proof.get("reused_evidence") is False
        and hip_consistency_proof.get("rocm_hip_required") is True
        and hip_consistency_proof.get("cpu_diagnostic_assembler_used") is False
        and hip_consistency_proof.get("production_hip_residual_jacobian_path") is True
        and hip_consistency_proof.get("consistent_residual_jacobian_newton_gate_passed")
        is True
        and not _string_list(hip_consistency_proof.get("receipt_blockers"))
        and not _string_list(hip_consistency_proof.get("runtime_blockers"))
    )

    worker_blockers = _dedupe_strings(
        [
            *[
                blocker
                for blocker in hip_consistency_blockers
                if blocker.startswith(hip_proof_worker_prefixes)
            ],
            *_string_list(worker.get("blockers")),
            *_string_list(worker.get("residual_jvp_worker_path_blockers")),
            *_string_list(worker.get("g1_closure_gate_blockers")),
        ]
    )
    worker_ready = bool(
        worker.get("ready") is True
        and worker.get("residual_jvp_worker_path_ready") is True
        and worker.get("g1_closure_gate_ready") is True
        and not worker_blockers
    )

    child_blockers = _dedupe_strings(
        [
            *_string_list(child_gate_evidence.get("blockers")),
            *_string_list(child_hip_residual_refresh_evidence.get("blockers")),
        ]
    )
    child_upstream_blockers = [
        requirement_id
        for requirement_id, ready in (
            ("full_load_checkpoint_1p0", checkpoint_ready),
            ("hip_consistent_residual_jacobian_newton_proof", hip_proof_ready),
            ("production_rocm_hip_residual_jvp_worker", worker_ready),
        )
        if not ready
    ]
    child_ready = bool(
        child_gate_evidence.get("ready") is True
        and child_hip_residual_refresh_evidence.get("ready") is True
    )

    requirements = [
        {
            "id": "full_load_checkpoint_1p0",
            "label": "Full-load 1.0 checkpoint candidate",
            "ready": checkpoint_ready,
            "status": "ready" if checkpoint_ready else "blocked",
            "acceptance_evidence": (
                "A loadable mgt-direct-residual-newton-state.v1 checkpoint with "
                "load_scale >= required_load_scale and no load-path provenance "
                "contradiction."
            ),
            "observed": {
                "required_load_scale": checkpoint_resolution_gate.get(
                    "required_load_scale"
                ),
                "highest_observed_load_scale": checkpoint_resolution_gate.get(
                    "highest_observed_load_scale"
                ),
                "highest_observed_gap_to_required_load_scale": (
                    checkpoint_resolution_gate.get(
                        "highest_observed_gap_to_required_load_scale"
                    )
                ),
                "full_load_candidate_count": checkpoint_resolution_gate.get(
                    "full_load_candidate_count"
                ),
                "load_path_provenance_passed": not load_path_provenance_blockers,
                "provenance_below_required_full_load": load_path_provenance.get(
                    "provenance_below_required_full_load"
                ),
            },
            "blockers": checkpoint_blockers,
            "next_action_ids": (
                []
                if checkpoint_ready
                else ["generate_full_load_1p0_checkpoint_candidate"]
            ),
            "rerun_command": (
                "python3 scripts/run_g1_full_load_hip_newton_lane.py "
                "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
            ),
        },
        {
            "id": "hip_consistent_residual_jacobian_newton_proof",
            "label": "HIP-required consistent residual/Jacobian Newton proof",
            "ready": hip_proof_ready,
            "status": "ready" if hip_proof_ready else "blocked",
            "acceptance_evidence": (
                "mgt_residual_jacobian_consistency_hip_required_probe.json passes "
                "the consistent residual/Jacobian Newton gate on the production "
                "ROCm/HIP path with no CPU diagnostic assembler or receipt blockers."
            ),
            "observed": {
                "path": hip_consistency_proof.get("path"),
                "present": hip_consistency_proof.get("present"),
                "source_state_fresh": hip_consistency_proof.get("source_state_fresh"),
                "source_state_kind": hip_consistency_proof.get("source_state_kind"),
                "consistent_residual_jacobian_newton_gate_passed": (
                    hip_consistency_proof.get(
                        "consistent_residual_jacobian_newton_gate_passed"
                    )
                ),
                "receipt_blocker_count": len(
                    _string_list(hip_consistency_proof.get("receipt_blockers"))
                ),
                "runtime_blocker_count": len(
                    _string_list(hip_consistency_proof.get("runtime_blockers"))
                ),
            },
            "blockers": hip_proof_blockers,
            "next_action_ids": (
                []
                if hip_proof_ready
                else ["close_consistent_residual_jacobian_newton_gate"]
            ),
            "rerun_command": (
                "python3 implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py "
                "--require-hip-residual-engine "
                "--checkpoint-npz <full-load-checkpoint.npz> "
                "--output-json implementation/phase1/release_evidence/productization/"
                "mgt_residual_jacobian_consistency_hip_required_probe.json"
            ),
        },
        {
            "id": "production_rocm_hip_residual_jvp_worker",
            "label": "Production ROCm/HIP residual/JVP worker",
            "ready": worker_ready,
            "status": "ready" if worker_ready else "blocked",
            "acceptance_evidence": (
                "The production_rocm_hip_residual_jvp_worker contract is ready, "
                "its residual/JVP path is ready, and its G1 closure gate is ready."
            ),
            "observed": {
                "worker_id": worker.get("worker_id"),
                "status": worker.get("status"),
                "ready": worker.get("ready"),
                "residual_jvp_worker_path_ready": worker.get(
                    "residual_jvp_worker_path_ready"
                ),
                "g1_closure_gate_ready": worker.get("g1_closure_gate_ready"),
            },
            "blockers": worker_blockers,
            "next_action_ids": (
                []
                if worker_ready
                else ["close_consistent_residual_jacobian_newton_gate"]
            ),
        },
        {
            "id": "full_load_child_direct_probe",
            "label": "Full-load child direct residual Newton probe",
            "ready": child_ready,
            "status": (
                "ready"
                if child_ready
                else (
                    "deferred_upstream_blocked"
                    if child_upstream_blockers
                    else "blocked"
                )
            ),
            "acceptance_evidence": (
                "The child direct residual Newton probe passes full-load closure, "
                "direct residual, relative increment, fallback-zero, material Newton "
                "breadth, consistent residual/Jacobian Newton, and HIP accepted-state "
                "residual refresh gates."
            ),
            "observed": {
                "child_gate_ready": child_gate_evidence.get("ready"),
                "hip_residual_refresh_ready": child_hip_residual_refresh_evidence.get(
                    "ready"
                ),
                "command": command,
            },
            "upstream_blocking_requirement_ids": child_upstream_blockers,
            "blockers": child_blockers,
            "next_action_ids": (
                []
                if child_ready
                else ["run_full_load_child_direct_probe_with_hip_refresh"]
            ),
        },
    ]
    ready_count = sum(1 for row in requirements if row["ready"] is True)
    deferred_count = sum(
        1 for row in requirements if row.get("status") == "deferred_upstream_blocked"
    )
    blocked_ids = [str(row["id"]) for row in requirements if row["ready"] is not True]
    active_requirement = next(
        (row for row in requirements if row.get("status") == "blocked"),
        next(
            (
                row
                for row in requirements
                if row.get("status") == "deferred_upstream_blocked"
            ),
            None,
        ),
    )
    return {
        "schema_version": "g1-full-load-hip-newton-terminal-requirement-breakdown.v1",
        "ready_requirement_count": ready_count,
        "requirement_count": len(requirements),
        "blocked_requirement_count": len(blocked_ids),
        "deferred_requirement_count": deferred_count,
        "blocked_requirement_ids": blocked_ids,
        "active_terminal_requirement_id": (
            active_requirement.get("id") if isinstance(active_requirement, dict) else None
        ),
        "requirements": requirements,
        "lane_ready_when_all_requirements_ready": ready_count == len(requirements),
        "claim_boundary": (
            "This breakdown is an operator handoff, not a promotion. It names the "
            "terminal G1 full-load HIP/Newton receipts that must all pass before "
            "the lane can claim readiness."
        ),
    }


def _direct_probe_command(
    *,
    checkpoint_npz: Path,
    output_json: Path,
    mgt_path: Path | None,
) -> list[str]:
    command = [
        sys.executable,
        str(DIRECT_PROBE),
        "--checkpoint-npz",
        str(checkpoint_npz),
        "--output-json",
        str(output_json),
        "--apply-shell-material-tangent",
        "--allow-state-dependent-shell-material-tangent-hip-replay",
        "--enable-matrix-free-global-krylov",
        "--matrix-free-global-krylov-batch-replay-backend",
        "hip_full_residual_resident",
        "--matrix-free-global-krylov-require-hip-batch-replay",
        "--matrix-free-global-krylov-linear-solver-backend",
        "torch_hip_gmres",
        "--matrix-free-global-krylov-scaling-mode",
        "residual_diagonal_displacement",
        "--matrix-free-global-krylov-preconditioner-mode",
        "current_tangent",
        "--matrix-free-global-krylov-full-assembly-trial-replay",
        "--enable-current-tangent-residual-row-correction",
        "--current-tangent-residual-row-use-residual-only-assembly",
        "--current-tangent-residual-row-per-state-batch-replay",
        "--current-tangent-residual-row-batch-replay-backend",
        "hip_full_residual",
        "--current-tangent-residual-row-require-hip-batch-replay",
        "--current-tangent-residual-row-jacobian-mode",
        "finite_difference",
    ]
    if mgt_path is not None:
        command.extend(["--mgt-path", str(mgt_path)])
    return command


def _load_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _frontier_non_promoting_evidence_context(
    evidence_sources: tuple[Path, ...],
) -> dict[str, Any]:
    source_rows: list[dict[str, Any]] = []
    selected_payload: dict[str, Any] = {}
    selected_source: Path | None = None
    for source in evidence_sources:
        payload = _load_json_payload(source)
        row = {
            "path": str(source),
            "present": bool(payload),
            "has_frontier_chain": isinstance(payload.get("frontier_chain"), list),
            "has_non_promoting_launch_receipts": isinstance(
                payload.get("non_promoting_launch_receipts"), list
            ),
        }
        source_rows.append(row)
        if selected_payload:
            continue
        if row["has_frontier_chain"] or row["has_non_promoting_launch_receipts"]:
            selected_payload = payload
            selected_source = source

    if not selected_payload:
        return {
            "schema_version": "g1-frontier-non-promoting-context.v1",
            "present": False,
            "source_path": None,
            "source_candidates": source_rows,
            "evidence_role": "missing_frontier_context",
            "promotes_g1_closure": False,
            "promotes_lane_status": False,
            "non_promoting_launch_receipt_count": 0,
            "frontier_chain_count": 0,
            "claim_boundary": (
                "No frontier/non-promoting status receipt was attached to this lane "
                "report, so no launch-only evidence can promote G1 closure."
            ),
        }

    frontier_chain = selected_payload.get("frontier_chain")
    frontier_chain = frontier_chain if isinstance(frontier_chain, list) else []
    non_promoting_launch_receipts = selected_payload.get("non_promoting_launch_receipts")
    non_promoting_launch_receipts = (
        non_promoting_launch_receipts
        if isinstance(non_promoting_launch_receipts, list)
        else []
    )
    latest_residual = _float_or_none(
        selected_payload.get("latest_frontier_direct_residual_inf_n")
    )
    tolerance = _float_or_none(selected_payload.get("direct_residual_gate_tolerance_n"))
    frontier_residual_above_tolerance = bool(
        latest_residual is not None
        and tolerance is not None
        and latest_residual > tolerance
    )
    return {
        "schema_version": "g1-frontier-non-promoting-context.v1",
        "present": True,
        "source_path": str(selected_source) if selected_source is not None else None,
        "source_status": selected_payload.get("status"),
        "source_contract_pass": bool(selected_payload.get("contract_pass") is True),
        "source_candidates": source_rows,
        "evidence_role": "non_promoting_partial_frontier_context",
        "promotes_g1_closure": False,
        "promotes_lane_status": False,
        "frontier_chain_count": len(frontier_chain),
        "latest_frontier_receipt": selected_payload.get("latest_frontier_receipt"),
        "latest_frontier_direct_residual_inf_n": latest_residual,
        "direct_residual_gate_tolerance_n": tolerance,
        "frontier_residual_above_tolerance": frontier_residual_above_tolerance,
        "non_promoting_launch_receipt_count": len(non_promoting_launch_receipts),
        "non_promoting_launch_receipts": non_promoting_launch_receipts,
        "source_blockers": (
            selected_payload.get("blockers")
            if isinstance(selected_payload.get("blockers"), list)
            else []
        ),
        "source_claim_boundary": selected_payload.get("claim_boundary"),
        "claim_boundary": (
            "Frontier and launch-only receipts are attached as non-promoting "
            "diagnostic context. They may explain why the lane is blocked, but "
            "they do not close full-load, material Newton, consistent residual/"
            "Jacobian Newton, production ROCm/HIP residency, or full G1."
        ),
    }


def _hip_consistency_proof_assessment(
    *,
    proof_json: Path,
    lane_source_commit_sha: str,
) -> tuple[dict[str, Any], list[str]]:
    payload = _load_json_payload(proof_json)
    blockers: list[str] = []
    if not payload:
        blockers.append("hip_consistency_proof_receipt_missing_or_unreadable")
    if payload.get("reused_evidence") is not False:
        blockers.append("hip_consistency_proof_reused_evidence_not_false")
    proof_source_commit = str(payload.get("source_commit_sha", "") or "")
    if not proof_source_commit:
        blockers.append("hip_consistency_proof_source_commit_sha_missing")
    source_state_fresh, source_state_kind, changed_paths = _source_state_freshness(
        proof_source_commit=proof_source_commit,
        lane_source_commit_sha=lane_source_commit_sha,
    )
    if proof_source_commit and not source_state_fresh:
        blockers.append("hip_consistency_proof_source_commit_sha_mismatch")
    if payload.get("rocm_hip_required") is not True:
        blockers.append("hip_consistency_proof_rocm_hip_not_required")
    if payload.get("cpu_diagnostic_assembler_used") is not False:
        blockers.append(
            "hip_consistency_proof_cpu_diagnostic_assembler_not_explicitly_false"
        )
    if payload.get("production_hip_residual_jacobian_path") is not True:
        blockers.append("hip_consistency_proof_production_hip_path_not_proven")
    if payload.get("consistent_residual_jacobian_newton_gate_passed") is not True:
        blockers.append("hip_consistency_proof_gate_not_passed")
    worker_contract = payload.get("production_rocm_hip_residual_jvp_worker")
    worker_contract = worker_contract if isinstance(worker_contract, dict) else {}
    if not worker_contract:
        blockers.append("hip_consistency_proof_worker_contract_missing")
    else:
        worker_blockers = _string_list(worker_contract.get("blockers"))
        residual_path_ready = worker_contract.get("residual_jvp_worker_path_ready")
        residual_path_blockers = _string_list(
            worker_contract.get("residual_jvp_worker_path_blockers")
        )
        g1_closure_gate_ready = worker_contract.get("g1_closure_gate_ready")
        g1_closure_gate_blockers = _string_list(
            worker_contract.get("g1_closure_gate_blockers")
        )
        if residual_path_ready is False or residual_path_blockers:
            blockers.append(
                "hip_consistency_proof_residual_jvp_worker_path_not_ready"
            )
        elif (
            residual_path_ready is not True
            and worker_contract.get("ready") is not True
        ):
            blockers.append(
                "hip_consistency_proof_production_rocm_hip_residual_jvp_worker_not_ready"
            )
        if g1_closure_gate_ready is False or g1_closure_gate_blockers:
            blockers.append("hip_consistency_proof_worker_g1_closure_gate_not_ready")
        for blocker in worker_blockers:
            blockers.append(f"hip_consistency_proof_worker::{blocker}")
    proof_blockers = payload.get("blockers")
    if isinstance(proof_blockers, list) and proof_blockers:
        blockers.append("hip_consistency_proof_has_blockers")
    preflight = payload.get("rocm_hip_runtime_preflight")
    preflight = preflight if isinstance(preflight, dict) else {}
    runtime_blockers_raw = preflight.get("runtime_blockers")
    runtime_blockers_list: list[str] = (
        [item for item in runtime_blockers_raw if isinstance(item, str) and item]
        if isinstance(runtime_blockers_raw, list)
        else []
    )
    for runtime_blocker in runtime_blockers_list:
        blockers.append(f"hip_consistency_proof_runtime::{runtime_blocker}")
    return {
        "path": str(proof_json),
        "present": proof_json.exists(),
        "status": payload.get("status"),
        "source_commit_sha": proof_source_commit,
        "source_state_fresh": source_state_fresh,
        "source_state_kind": source_state_kind,
        "changed_paths_since_source_commit": changed_paths,
        "reused_evidence": payload.get("reused_evidence"),
        "rocm_hip_required": payload.get("rocm_hip_required"),
        "execution_mode": payload.get("execution_mode"),
        "cpu_diagnostic_assembler_used": payload.get("cpu_diagnostic_assembler_used"),
        "production_hip_residual_jacobian_path": payload.get(
            "production_hip_residual_jacobian_path"
        ),
        "consistent_residual_jacobian_newton_gate_passed": payload.get(
            "consistent_residual_jacobian_newton_gate_passed"
        ),
        "production_rocm_hip_residual_jvp_worker": {
            "present": bool(worker_contract),
            "ready": worker_contract.get("ready") is True,
            "status": worker_contract.get("status"),
            "worker_id": worker_contract.get("worker_id"),
            "blockers": _string_list(worker_contract.get("blockers")),
            "residual_jvp_worker_path_ready": worker_contract.get(
                "residual_jvp_worker_path_ready"
            ),
            "residual_jvp_worker_path_blockers": _string_list(
                worker_contract.get("residual_jvp_worker_path_blockers")
            ),
            "g1_closure_gate_ready": worker_contract.get("g1_closure_gate_ready"),
            "g1_closure_gate_blockers": _string_list(
                worker_contract.get("g1_closure_gate_blockers")
            ),
        },
        "receipt_blockers": proof_blockers if isinstance(proof_blockers, list) else [],
        "runtime_blockers": runtime_blockers_list,
    }, blockers


def build_lane_report(
    *,
    checkpoint_npz: Path | None = None,
    output_json: Path = DEFAULT_CHILD_OUT,
    mgt_path: Path | None = None,
    required_load_scale: float = 1.0,
    full_load_tolerance: float = 1.0e-12,
    dry_run: bool = False,
    evidence_sources: tuple[Path, ...] = CHECKPOINT_EVIDENCE_SOURCES,
    hip_consistency_proof_json: Path = DEFAULT_HIP_CONSISTENCY_PROOF,
    workspace_checkpoint_scan_root: Path | None = None,
) -> tuple[dict[str, Any], int]:
    generated_at = _now_utc_iso()
    resolved_checkpoint, checkpoint_resolution = _resolve_checkpoint(
        requested=checkpoint_npz,
        required_load_scale=required_load_scale,
        full_load_tolerance=full_load_tolerance,
        sources=evidence_sources,
    )
    if resolved_checkpoint is None:
        checkpoint_meta = {"path": None, "load_scale": None}
        blockers = ["auto_select_no_loadable_candidates"]
    else:
        checkpoint_meta, blockers = _load_checkpoint_meta(resolved_checkpoint)
    observed_load_scale = checkpoint_meta.get("load_scale")
    full_load_input_pass = bool(
        observed_load_scale is not None
        and float(observed_load_scale) >= float(required_load_scale) - float(full_load_tolerance)
    )
    if not full_load_input_pass and "checkpoint_load_scale_missing" not in blockers:
        blockers.append("checkpoint_load_scale_below_required_full_load")
    checkpoint_resolution_gate, checkpoint_resolution_gate_blockers = (
        _checkpoint_resolution_gate(
            checkpoint_resolution=checkpoint_resolution,
            checkpoint_meta=checkpoint_meta,
            required_load_scale=float(required_load_scale),
            full_load_tolerance=float(full_load_tolerance),
        )
    )
    for blocker in checkpoint_resolution_gate_blockers:
        if blocker not in blockers:
            blockers.append(blocker)
    checkpoint_load_path_blockers = _load_path_provenance_blockers(
        checkpoint_meta=checkpoint_meta,
        required_load_scale=float(required_load_scale),
        full_load_tolerance=float(full_load_tolerance),
    )
    load_path_provenance, evidence_load_path_blockers = (
        _load_path_provenance_assessment(
            checkpoint_resolution=checkpoint_resolution,
            required_load_scale=float(required_load_scale),
            full_load_tolerance=float(full_load_tolerance),
        )
    )
    load_path_provenance_blockers = [
        *checkpoint_load_path_blockers,
        *evidence_load_path_blockers,
    ]
    load_path_provenance_pass = not load_path_provenance_blockers
    command = _direct_probe_command(
        checkpoint_npz=resolved_checkpoint or DEFAULT_CHECKPOINT,
        output_json=output_json,
        mgt_path=mgt_path,
    )
    source_commit_sha = _git_head()
    hip_consistency_proof, hip_consistency_blockers = _hip_consistency_proof_assessment(
        proof_json=hip_consistency_proof_json,
        lane_source_commit_sha=source_commit_sha,
    )
    workspace_checkpoint_inventory = _workspace_checkpoint_inventory(
        scan_root=workspace_checkpoint_scan_root,
        required_load_scale=float(required_load_scale),
        full_load_tolerance=float(full_load_tolerance),
    )
    frontier_non_promoting_context = _frontier_non_promoting_evidence_context(
        evidence_sources
    )
    checksum_inputs = [
        *(
            path
            for path in (checkpoint_npz, resolved_checkpoint, mgt_path, hip_consistency_proof_json)
            if path is not None
        ),
        *evidence_sources,
        DIRECT_PROBE,
    ]
    initial_child_hip_residual_refresh_evidence = _child_hip_residual_refresh_evidence({})
    initial_child_gate_evidence = _child_gate_evidence(
        {},
        {},
        required_load_scale=float(required_load_scale),
        full_load_tolerance=float(full_load_tolerance),
    )
    blocker_partition = _g1_lane_blocker_partition(
        checkpoint_resolution_gate=checkpoint_resolution_gate,
        load_path_provenance=load_path_provenance,
        load_path_provenance_blockers=load_path_provenance_blockers,
        hip_consistency_proof=hip_consistency_proof,
        child_gate_evidence=initial_child_gate_evidence,
        child_hip_residual_refresh_evidence=initial_child_hip_residual_refresh_evidence,
    )
    lane_next_actions = _g1_lane_next_actions(
        checkpoint_resolution_gate=checkpoint_resolution_gate,
        workspace_checkpoint_inventory=workspace_checkpoint_inventory,
        hip_consistency_proof=hip_consistency_proof,
        child_gate_evidence=initial_child_gate_evidence,
        child_hip_residual_refresh_evidence=initial_child_hip_residual_refresh_evidence,
        command=command,
    )
    terminal_requirement_breakdown = _g1_lane_terminal_requirement_breakdown(
        checkpoint_resolution_gate=checkpoint_resolution_gate,
        load_path_provenance=load_path_provenance,
        load_path_provenance_blockers=load_path_provenance_blockers,
        hip_consistency_proof=hip_consistency_proof,
        hip_consistency_blockers=hip_consistency_blockers,
        child_gate_evidence=initial_child_gate_evidence,
        child_hip_residual_refresh_evidence=initial_child_hip_residual_refresh_evidence,
        command=command,
    )
    base_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_commit_sha": source_commit_sha,
        "engine_version": ENGINE_VERSION,
        "input_checksums": input_checksums(checksum_inputs, repo_root=ROOT),
        "reused_evidence": False,
        "checkpoint": checkpoint_meta,
        "checkpoint_resolution": checkpoint_resolution,
        "checkpoint_resolution_gate": checkpoint_resolution_gate,
        "required_load_scale": float(required_load_scale),
        "full_load_tolerance": float(full_load_tolerance),
        "full_load_input_pass": full_load_input_pass,
        "load_path_provenance": load_path_provenance,
        "load_path_provenance_pass": load_path_provenance_pass,
        "workspace_checkpoint_inventory": workspace_checkpoint_inventory,
        "frontier_non_promoting_evidence": frontier_non_promoting_context,
        "dry_run": bool(dry_run),
        "command": command,
        "hip_consistency_proof": hip_consistency_proof,
        "blocker_partition": blocker_partition,
        "lane_next_actions": lane_next_actions,
        "terminal_requirement_breakdown": terminal_requirement_breakdown,
        "child_hip_residual_refresh_evidence": initial_child_hip_residual_refresh_evidence,
        "child_gate_evidence": initial_child_gate_evidence,
        "child_safety_requirements": [
            "child_reused_evidence_false",
            "child_source_commit_matches_lane",
            "child_observed_load_scale_at_required_full_load",
            "child_hip_residual_engine_contract_passed",
            "child_consistent_residual_jacobian_newton_passed",
            "external_hip_consistency_proof_gate_passed",
            "child_material_newton_breadth_passed",
            "child_cpu_acceptance_refresh_not_blocked",
            "child_fallback_zero_passed",
            "child_hip_required_accepted_residual_refresh_proven",
        ],
        "claim_boundary": (
            "This lane is a strict execution wrapper for representative full-load "
            "G1 HIP Newton evidence. It does not synthesize residual, increment, "
            "consistent residual/Jacobian Newton closure, material Newton breadth, "
            "customer, validation, or ROCm/HIP closure evidence. "
            "The child probe must explicitly prove full-load closure, HIP residual residency, "
            "consistent residual/Jacobian Newton closure, fallback-zero behavior, "
            "and material Newton breadth. The separate HIP-required residual/Jacobian "
            "consistency receipt must also pass without blockers. A checkpoint below "
            "load_scale 1.0 is blocked before execution, and a checkpoint that claims "
            "load_scale >= 1.0 is also blocked when its metadata exposes an accepted "
            "frontier below the required full load or a failed bracket below full load."
        ),
    }
    if blockers:
        return {
            **base_payload,
            "status": "blocked",
            "contract_pass": False,
            "blockers": [*blockers, *hip_consistency_blockers],
            "child_exit_code": None,
        }, 1
    if load_path_provenance_blockers:
        return {
            **base_payload,
            "status": "blocked",
            "contract_pass": False,
            "blockers": [*load_path_provenance_blockers, *hip_consistency_blockers],
            "child_exit_code": None,
        }, 1
    if hip_consistency_blockers:
        return {
            **base_payload,
            "status": "blocked",
            "contract_pass": False,
            "blockers": list(hip_consistency_blockers),
            "child_exit_code": None,
        }, 1
    if dry_run:
        return {
            **base_payload,
            "status": "ready_to_run",
            "contract_pass": False,
            "blockers": [],
            "child_exit_code": None,
        }, 0

    output_json.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, check=False)
    child_payload: dict[str, Any] = {}
    if output_json.exists():
        try:
            loaded = json.loads(output_json.read_text(encoding="utf-8"))
            child_payload = loaded if isinstance(loaded, dict) else {}
        except Exception:
            child_payload = {}
    child_gate = child_payload.get("gate_assessment") if isinstance(child_payload, dict) else {}
    child_gate = child_gate if isinstance(child_gate, dict) else {}
    child_hip_residual_refresh_evidence = _child_hip_residual_refresh_evidence(
        child_payload
    )
    child_gate_evidence = _child_gate_evidence(
        child_payload,
        child_gate,
        required_load_scale=float(required_load_scale),
        full_load_tolerance=float(full_load_tolerance),
    )
    safety_blockers = _child_safety_blockers(
        child_payload=child_payload,
        child_gate=child_gate,
        lane_source_commit_sha=base_payload["source_commit_sha"],
        required_load_scale=float(required_load_scale),
        full_load_tolerance=float(full_load_tolerance),
    )
    safety_blockers.extend(hip_consistency_blockers)
    child_ready = bool(
        result.returncode == 0
        and not safety_blockers
        and child_payload.get("direct_residual_newton_ready") is True
        and child_gate.get("full_load_closure_passed") is True
        and child_gate.get("fallback_zero_passed") is True
    )
    child_blockers = child_payload.get("blockers") if isinstance(child_payload, dict) else []
    final_blocker_partition = _g1_lane_blocker_partition(
        checkpoint_resolution_gate=checkpoint_resolution_gate,
        load_path_provenance=load_path_provenance,
        load_path_provenance_blockers=load_path_provenance_blockers,
        hip_consistency_proof=hip_consistency_proof,
        child_gate_evidence=child_gate_evidence,
        child_hip_residual_refresh_evidence=child_hip_residual_refresh_evidence,
    )
    final_lane_next_actions = _g1_lane_next_actions(
        checkpoint_resolution_gate=checkpoint_resolution_gate,
        workspace_checkpoint_inventory=workspace_checkpoint_inventory,
        hip_consistency_proof=hip_consistency_proof,
        child_gate_evidence=child_gate_evidence,
        child_hip_residual_refresh_evidence=child_hip_residual_refresh_evidence,
        command=command,
    )
    final_terminal_requirement_breakdown = _g1_lane_terminal_requirement_breakdown(
        checkpoint_resolution_gate=checkpoint_resolution_gate,
        load_path_provenance=load_path_provenance,
        load_path_provenance_blockers=load_path_provenance_blockers,
        hip_consistency_proof=hip_consistency_proof,
        hip_consistency_blockers=hip_consistency_blockers,
        child_gate_evidence=child_gate_evidence,
        child_hip_residual_refresh_evidence=child_hip_residual_refresh_evidence,
        command=command,
    )
    return {
        **base_payload,
        "status": "ready" if child_ready else "blocked",
        "contract_pass": child_ready,
        "blockers": [] if child_ready else [
            *safety_blockers,
            *(child_blockers if isinstance(child_blockers, list) else []),
            "g1_full_load_hip_newton_child_not_ready",
        ],
        "child_exit_code": int(result.returncode),
        "child_output_json": str(output_json),
        "child_hip_residual_refresh_evidence": child_hip_residual_refresh_evidence,
        "child_gate_evidence": child_gate_evidence,
        "blocker_partition": final_blocker_partition,
        "lane_next_actions": final_lane_next_actions,
        "terminal_requirement_breakdown": final_terminal_requirement_breakdown,
    }, 0 if child_ready else 1


def _child_safety_blockers(
    *,
    child_payload: dict[str, Any],
    child_gate: dict[str, Any],
    lane_source_commit_sha: str,
    required_load_scale: float,
    full_load_tolerance: float,
) -> list[str]:
    """Return safety blockers that prevent diagnostic or reused child evidence from
    being promoted as full G1 closure."""
    blockers: list[str] = []
    if child_payload.get("reused_evidence") is not False:
        blockers.append("child_reused_evidence_not_false")
    child_source_commit = str(child_payload.get("source_commit_sha", "") or "")
    if not child_source_commit:
        blockers.append("child_source_commit_sha_missing")
    elif lane_source_commit_sha and child_source_commit != lane_source_commit_sha:
        blockers.append("child_source_commit_sha_mismatch")
    closure_gate = child_gate.get("full_load_closure_gate") if isinstance(child_gate, dict) else {}
    closure_gate = closure_gate if isinstance(closure_gate, dict) else {}
    observed_child_load = closure_gate.get("observed_load_scale")
    try:
        observed_load_value = float(observed_child_load)
    except (TypeError, ValueError):
        observed_load_value = None
    if observed_load_value is None or not (
        observed_load_value >= float(required_load_scale) - float(full_load_tolerance)
    ):
        blockers.append("child_observed_load_scale_below_required_full_load")
    if child_payload.get("direct_residual_newton_ready") is not True:
        blockers.append("child_direct_residual_newton_ready_not_proven")
    if child_gate.get("full_load_closure_passed") is not True:
        blockers.append("child_full_load_closure_not_proven")
    if child_gate.get("direct_residual_gate_passed") is not True:
        blockers.append("child_direct_residual_gate_not_proven")
    if child_gate.get("relative_increment_gate_passed") is not True:
        blockers.append("child_relative_increment_gate_not_proven")
    residual_contract = child_payload.get("residual_contract")
    residual_contract = residual_contract if isinstance(residual_contract, dict) else {}
    if residual_contract.get("hip_residual_engine_contract_passed") is not True:
        blockers.append("child_hip_residual_engine_contract_not_proven")
    consistent_jacobian_passed = bool(
        child_gate.get("consistent_residual_jacobian_newton_passed") is True
    )
    if not consistent_jacobian_passed:
        blockers.append("child_consistent_residual_jacobian_newton_not_proven")
    if (
        residual_contract.get("consistent_residual_jacobian_newton_gate_passed")
        is True
        and not consistent_jacobian_passed
    ):
        blockers.append("child_consistent_residual_jacobian_contract_gate_conflict")
    material_newton_passed = bool(child_gate.get("material_newton_breadth_passed") is True)
    if not material_newton_passed:
        blockers.append("child_material_newton_breadth_not_proven")
    if (
        residual_contract.get("material_newton_gate_passed") is True
        or residual_contract.get("state_dependent_material_newton_closure_passed")
        is True
    ) and not material_newton_passed:
        blockers.append("child_material_newton_contract_gate_conflict")
    if child_gate.get("cpu_acceptance_refresh_closure_blocked") is True:
        blockers.append("child_cpu_acceptance_refresh_closure_blocked")
    if child_gate.get("fallback_zero_passed") is not True:
        blockers.append("child_fallback_zero_not_proven")
    blockers.extend(_child_hip_residual_refresh_blockers(child_payload))
    blockers.extend(_child_gate_audit_consistency_blockers(child_gate))
    return blockers


def _child_hip_residual_refresh_blockers(child_payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for component_key, blocker_prefix in HIP_CHILD_RESIDUAL_COMPONENTS:
        component = child_payload.get(component_key)
        if not isinstance(component, dict):
            blockers.append(f"{blocker_prefix}_component_missing")
            continue
        if not (
            component.get("require_hip_batch_replay")
            or component.get("require_hip_krylov_solver")
        ):
            blockers.append(f"{blocker_prefix}_hip_not_required")
        if component.get("promoted_to_final_state") is not True:
            blockers.append(f"{blocker_prefix}_not_promoted_to_final_state")
        backend = str(component.get("accepted_state_refresh_backend", "") or "")
        if (
            backend not in HIP_RESIDUAL_REPLAY_BACKENDS
            or component.get("accepted_state_refresh_hip_used") is not True
        ):
            blockers.append(f"{blocker_prefix}_hip_residual_refresh_not_proven")
        if component.get("accepted_state_refresh_cpu_used") is True:
            blockers.append(f"{blocker_prefix}_cpu_residual_refresh_used")
    return blockers


def _child_gate_evidence(
    child_payload: dict[str, Any],
    child_gate: dict[str, Any],
    *,
    required_load_scale: float,
    full_load_tolerance: float,
) -> dict[str, Any]:
    closure_gate = child_gate.get("full_load_closure_gate")
    closure_gate = closure_gate if isinstance(closure_gate, dict) else {}
    observed_child_load = closure_gate.get("observed_load_scale")
    try:
        observed_load_value = float(observed_child_load)
    except (TypeError, ValueError):
        observed_load_value = None
    load_scale_passed = bool(
        observed_load_value is not None
        and observed_load_value >= float(required_load_scale) - float(full_load_tolerance)
    )
    blockers: list[str] = []
    if child_payload.get("direct_residual_newton_ready") is not True:
        blockers.append("child_direct_residual_newton_ready_not_proven")
    if child_gate.get("full_load_closure_passed") is not True:
        blockers.append("child_full_load_closure_not_proven")
    if not load_scale_passed:
        blockers.append("child_observed_load_scale_below_required_full_load")
    if child_gate.get("direct_residual_gate_passed") is not True:
        blockers.append("child_direct_residual_gate_not_proven")
    if child_gate.get("relative_increment_gate_passed") is not True:
        blockers.append("child_relative_increment_gate_not_proven")
    if child_gate.get("fallback_zero_passed") is not True:
        blockers.append("child_fallback_zero_not_proven")
    if child_gate.get("material_newton_breadth_passed") is not True:
        blockers.append("child_material_newton_breadth_not_proven")
    if child_gate.get("consistent_residual_jacobian_newton_passed") is not True:
        blockers.append("child_consistent_residual_jacobian_newton_not_proven")
    residual_contract = child_payload.get("residual_contract")
    residual_contract = residual_contract if isinstance(residual_contract, dict) else {}
    if (
        residual_contract.get("consistent_residual_jacobian_newton_gate_passed")
        is True
        and child_gate.get("consistent_residual_jacobian_newton_passed") is not True
    ):
        blockers.append("child_consistent_residual_jacobian_contract_gate_conflict")
    if (
        residual_contract.get("material_newton_gate_passed") is True
        or residual_contract.get("state_dependent_material_newton_closure_passed")
        is True
    ) and child_gate.get("material_newton_breadth_passed") is not True:
        blockers.append("child_material_newton_contract_gate_conflict")
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "g1-child-gate-evidence.v1",
        "ready": not blockers,
        "blockers": blockers,
        "direct_residual_newton_ready": child_payload.get(
            "direct_residual_newton_ready"
        )
        is True,
        "full_load_closure_passed": child_gate.get("full_load_closure_passed")
        is True,
        "direct_residual_gate_passed": child_gate.get("direct_residual_gate_passed")
        is True,
        "relative_increment_gate_passed": (
            child_gate.get("relative_increment_gate_passed") is True
        ),
        "fallback_zero_passed": child_gate.get("fallback_zero_passed") is True,
        "material_newton_breadth_passed": (
            child_gate.get("material_newton_breadth_passed") is True
        ),
        "consistent_residual_jacobian_newton_passed": (
            child_gate.get("consistent_residual_jacobian_newton_passed") is True
        ),
        "observed_load_scale": observed_load_value,
        "required_load_scale": float(required_load_scale),
        "full_load_tolerance": float(full_load_tolerance),
        "load_scale_passed": load_scale_passed,
    }


def _child_hip_residual_refresh_evidence(
    child_payload: dict[str, Any],
) -> dict[str, Any]:
    components: dict[str, Any] = {}
    for component_key, _blocker_prefix in HIP_CHILD_RESIDUAL_COMPONENTS:
        component = child_payload.get(component_key)
        if not isinstance(component, dict):
            components[component_key] = {
                "present": False,
                "ready": False,
                "hip_required": False,
                "promoted_to_final_state": False,
                "accepted_state_refresh_backend": "",
                "accepted_state_refresh_hip_used": False,
                "accepted_state_refresh_cpu_used": False,
            }
            continue
        backend = str(component.get("accepted_state_refresh_backend", "") or "")
        hip_required = bool(
            component.get("require_hip_batch_replay")
            or component.get("require_hip_krylov_solver")
        )
        promoted = component.get("promoted_to_final_state") is True
        hip_refresh_used = component.get("accepted_state_refresh_hip_used") is True
        cpu_refresh_used = component.get("accepted_state_refresh_cpu_used") is True
        ready = bool(
            hip_required
            and promoted
            and backend in HIP_RESIDUAL_REPLAY_BACKENDS
            and hip_refresh_used
            and not cpu_refresh_used
        )
        components[component_key] = {
            "present": True,
            "ready": ready,
            "hip_required": hip_required,
            "promoted_to_final_state": promoted,
            "accepted_state_refresh_backend": backend,
            "accepted_state_refresh_hip_used": hip_refresh_used,
            "accepted_state_refresh_cpu_used": cpu_refresh_used,
        }
    blockers = _child_hip_residual_refresh_blockers(child_payload)
    return {
        "schema_version": "g1-child-hip-residual-refresh-evidence.v1",
        "ready": not blockers,
        "blockers": blockers,
        "components": components,
    }


def _child_gate_audit_consistency_blockers(child_gate: dict[str, Any]) -> list[str]:
    """Return blockers when a child gate advertises a positive verdict but the
    matching audit-level evidence contradicts it.

    The G1 readiness check accepts ``fallback_zero_passed is True``,
    ``material_newton_breadth_passed is True``, and
    ``consistent_residual_jacobian_newton_passed is True`` as proof that those
    closures are real. A hand-crafted or buggy child payload that flips those
    flags while the underlying audit still records non-zero boundaries or a
    non-empty blockers list would otherwise be promoted as full G1 closure.
    This guard cross-validates the gate-level verdict against the matching
    audit detail so such an inconsistency is recorded as an actionable
    blocker instead of being silently accepted.
    """
    blockers: list[str] = []
    fallback_zero_audit = child_gate.get("fallback_zero_audit")
    fallback_zero_audit = fallback_zero_audit if isinstance(fallback_zero_audit, dict) else {}
    audit_fallback_passed = fallback_zero_audit.get("fallback_zero_passed")
    boundaries = fallback_zero_audit.get("fallback_zero_boundaries")
    boundary_list = boundaries if isinstance(boundaries, list) else []
    boundary_count = fallback_zero_audit.get("fallback_zero_boundary_count")
    if (
        child_gate.get("fallback_zero_passed") is True
        and boundary_list
    ):
        blockers.append("child_fallback_zero_boundaries_present_with_passed_flag")
    if (
        child_gate.get("fallback_zero_passed") is True
        and audit_fallback_passed is False
    ):
        blockers.append("child_fallback_zero_gate_audit_mismatch")
    if isinstance(boundary_count, (int, float)) and int(boundary_count) != len(boundary_list):
        blockers.append("child_fallback_zero_boundary_count_mismatch")
    material_blockers = child_gate.get("material_newton_breadth_blockers")
    if (
        child_gate.get("material_newton_breadth_passed") is True
        and isinstance(material_blockers, list)
        and material_blockers
    ):
        blockers.append("child_material_newton_breadth_blockers_present_with_passed_flag")
    consistent_blockers = child_gate.get("consistent_residual_jacobian_newton_blockers")
    if (
        child_gate.get("consistent_residual_jacobian_newton_passed") is True
        and isinstance(consistent_blockers, list)
        and consistent_blockers
    ):
        blockers.append(
            "child_consistent_residual_jacobian_newton_blockers_present_with_passed_flag"
        )
    return blockers


def _checkpoint_path_arg(value: str) -> Path | None:
    stripped = value.strip()
    if stripped.lower() == "auto":
        return None
    return Path(stripped)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint-npz",
        type=_checkpoint_path_arg,
        default=None,
        help=(
            "Path to the G1 checkpoint .npz to feed the direct residual Newton probe. "
            "Omit this option, or pass the literal value 'auto', to scan configured "
            "status/manifest JSON files and select the highest-load candidate."
        ),
    )
    parser.add_argument("--child-output-json", type=Path, default=DEFAULT_CHILD_OUT)
    parser.add_argument("--mgt-path", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--required-load-scale", type=float, default=1.0)
    parser.add_argument("--full-load-tolerance", type=float, default=1.0e-12)
    parser.add_argument(
        "--hip-consistency-proof-json",
        type=Path,
        default=DEFAULT_HIP_CONSISTENCY_PROOF,
        help=(
            "HIP-required residual/Jacobian consistency receipt that must pass before "
            "the G1 lane can be promoted."
        ),
    )
    parser.add_argument(
        "--workspace-checkpoint-scan-root",
        type=Path,
        default=PRODUCTIZATION,
        help=(
            "Directory scanned for diagnostic local .npz checkpoint load-scale "
            "inventory. The scan is non-promoting and does not affect G1 closure."
        ),
    )
    parser.add_argument(
        "--skip-workspace-checkpoint-inventory",
        action="store_true",
        help="Disable the diagnostic workspace checkpoint inventory scan.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload, exit_code = build_lane_report(
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.child_output_json,
        mgt_path=args.mgt_path,
        required_load_scale=args.required_load_scale,
        full_load_tolerance=args.full_load_tolerance,
        dry_run=args.dry_run,
        hip_consistency_proof_json=args.hip_consistency_proof_json,
        workspace_checkpoint_scan_root=(
            None
            if args.skip_workspace_checkpoint_inventory
            else args.workspace_checkpoint_scan_root
        ),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"G1 full-load HIP Newton lane: {payload['status']}")
    return exit_code if args.fail_blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
