#!/usr/bin/env python3
"""Build the G1 shell-material budgeted continuation status receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "mgt-g1-shell-material-budgeted-continuation-status.v3"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "mgt_g1_followup387_shell_material_budgeted_continuation_status.json"
DEFAULT_DIRECT_RESIDUAL_TOLERANCE_N = 5.0e-4
REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_FRONTIER_CHAIN = (
    "mgt_direct_residual_shell_material_tangent_base_followup379_probe.json",
    "mgt_direct_residual_shell_material_tangent_rowcorr_min_followup380_probe.json",
    "mgt_shell_material_rowcorr_budget_controller_followup383_target2_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup384_target2_support4_compact_checkpoint.json",
    "mgt_shell_material_rowcorr_budget_controller_followup385_continue_target2_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup386_continue_target2_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup387_target4_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup388_multistep_target4_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup389_multistep_target4_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup391_multistep_target4_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup392_multistep_target4_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup393_multistep_target4_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup394_multistep_target4_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup395_multistep_target4_support4.json",
    "mgt_direct_residual_shell_material_adaptive_global_krylov_followup396_smoke.json",
    "mgt_direct_residual_shell_material_adaptive_global_krylov_followup397_compact_smoke.json",
    "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup401_target4_support4_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup402_target4_support4_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup403_target4_support4_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup405_target8_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup405_target8_support4_cpu_continuation_candidate1_target8_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup407_target16_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup407_target16_support4_cpu_continuation_candidate1_target16_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support4_cpu_continuation_candidate1_target16_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup409_target16_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup409_target16_support4_cpu_continuation_candidate1_target16_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup410_target16_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup410_target16_support4_cpu_continuation_candidate1_target16_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup411_target16_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup411_target16_support4_cpu_continuation_candidate1_target16_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup412_target16_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup412_target16_support4_cpu_continuation_candidate1_target16_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup413_target16_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup413_target16_support4_cpu_continuation_candidate1_target16_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup414_target16_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup414_target16_support4_cpu_continuation_candidate1_target16_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup415_target16_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup415_target16_support4_cpu_continuation_candidate1_target16_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup416_target32_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup416_target32_support4_cpu_continuation_candidate1_target32_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup417_target32_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup417_target32_support4_cpu_continuation_candidate1_target32_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_candidate1_target32_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup419_target64_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup419_target64_support4_cpu_continuation_candidate1_target64_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup420_target64_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup420_target64_support4_cpu_continuation_candidate1_target64_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup421_target64_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup421_target64_support4_cpu_continuation_candidate1_target64_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup422_target64_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup422_target64_support4_cpu_continuation_candidate1_target64_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup423_target64_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup423_target64_support4_cpu_continuation_candidate1_target64_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup424_target64_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup424_target64_support4_cpu_continuation_candidate1_target64_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup425_target64_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup425_target64_support4_cpu_continuation_candidate1_target64_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup427_target128_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup427_target128_support4_cpu_continuation_candidate1_target128_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup428_target128_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup428_target128_support4_cpu_continuation_candidate1_target128_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_candidate1_target128_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_candidate1_target128_support8.json",
)
DEFAULT_COUNTER_EVIDENCE = (
    "mgt_shell_material_rowcorr_budget_controller_followup382_support8_checkpointed.json",
    "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support8_cpu_continuation_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup408_target16_support8_cpu_continuation_candidate1_target16_support8.json",
)
DEFAULT_NON_PROMOTING_LAUNCH_RECEIPTS = (
    "mgt_shell_material_rowcorr_budget_controller_followup390_multistep_target4_support4_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup390_multistep_target4_support4_candidate1_target4_support4.json",
    "mgt_shell_material_rowcorr_budget_controller_followup399_target_rows_strict_hip_smoke.json",
    "mgt_g1_followup400_strict_hip_target_rows_alternating_smoke.json",
    "mgt_shell_material_rowcorr_budget_controller_followup404_target4_support4_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup406_target8_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup426_target64_support4_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup430_target256_support4_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup432_target128_support16_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup433_target192_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup434_target96_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup435_bending_drilling_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup436_normal_rows_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup437_geometry_normal_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup438_geometry_normal_bending_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup439_shell_element_blocks_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup440_element_blocks_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup441_frame_element_blocks_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup442_node_blocks_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup443_current_component_rows_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup444_frontier_component_rows_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup445_fd_largest_rows_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup446_residual_weighted_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup447_fd_target_rows_support8_cpu_continuation.json",
    "mgt_shell_material_rowcorr_budget_controller_followup448_fd_residual_weighted_support8_cpu_continuation.json",
)
DEFAULT_PENDING_LAUNCH_ONLY_RECEIPTS: tuple[str, ...] = ()
DEFAULT_DUPLICATE_ALIAS_RECEIPTS: tuple[tuple[str, str], ...] = (
    (
        "mgt_shell_material_rowcorr_budget_controller_followup436_shell_normal_support8_cpu_continuation.json",
        "mgt_shell_material_rowcorr_budget_controller_followup436_normal_rows_support8_cpu_continuation.json",
    ),
)
DEFAULT_ROW_TARGET_MODES = (
    "largest_rows",
    "residual_node_blocks",
    "residual_element_blocks",
    "residual_frame_element_blocks",
    "residual_shell_element_blocks",
    "residual_shell_bending_drilling_rows",
    "residual_shell_normal_rows",
    "residual_shell_geometry_normal_rows",
    "residual_shell_geometry_normal_bending_rows",
    "frontier_component_rows",
    "current_component_rows",
)
DEFAULT_LARGEST_ROWS_OPERATOR_STRATEGIES = (
    {
        "id": "current_tangent_row_strongest_target128_support8",
        "row_target_mode": "largest_rows",
        "row_jacobian_mode": "current_tangent",
        "row_support_selection": "row_strongest",
        "target_row_count": 128,
        "support_column_count": 8,
    },
    {
        "id": "current_tangent_residual_weighted_target128_support8",
        "row_target_mode": "largest_rows",
        "row_jacobian_mode": "current_tangent",
        "row_support_selection": "residual_weighted",
        "target_row_count": 128,
        "support_column_count": 8,
    },
    {
        "id": "finite_difference_row_strongest_target128_support8",
        "row_target_mode": "largest_rows",
        "row_jacobian_mode": "finite_difference",
        "row_support_selection": "row_strongest",
        "target_row_count": 128,
        "support_column_count": 8,
    },
    {
        "id": "finite_difference_target_rows_target128_support8",
        "row_target_mode": "largest_rows",
        "row_jacobian_mode": "finite_difference",
        "row_support_selection": "target_rows",
        "target_row_count": 128,
        "support_column_count": 8,
    },
    {
        "id": "finite_difference_residual_weighted_target128_support8",
        "row_target_mode": "largest_rows",
        "row_jacobian_mode": "finite_difference",
        "row_support_selection": "residual_weighted",
        "target_row_count": 128,
        "support_column_count": 8,
    },
)
DEFAULT_HIP_RESIDUAL_ROW_BACKEND_RECEIPTS = (
    "mgt_rocm_backend_newton_row_integration_followup67_summary.json",
    "mgt_direct_residual_hip_row_backend_followup68_69_summary.json",
    "mgt_direct_residual_hip_largest_rows_followup70_72_summary.json",
    "mgt_direct_residual_hip_largest_rows_followup73_74_saturation_summary.json",
)
DEFAULT_CONSISTENT_RESIDUAL_JACOBIAN_RECEIPTS = (
    "mgt_residual_jacobian_consistency_hip_required_probe.json",
    "mgt_residual_jacobian_attached_policy_global_krylov_followup43_frontier_probe.json",
    "mgt_residual_jacobian_attached_policy_global_krylov_post_shell_followup62_frontier_probe.json",
    "mgt_residual_jacobian_attached_policy_hip_largest_rows_followup69_frontier_probe.json",
    "mgt_residual_jacobian_attached_policy_hip_largest_rows_followup71_frontier_probe.json",
    "mgt_residual_jacobian_attached_policy_hip_largest_rows_followup73_frontier_probe.json",
    "mgt_residual_jacobian_physical_audit_followup85_86_summary.json",
    "mgt_cached_residual_jvp_top96_multi_ridge_followup354_361_after_total_scaled_component_fd_hip_latest_only_controller_summary.json",
)
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _input_checksums(paths: list[Path]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in paths:
        checksums[str(path)] = _sha256(path) if path.exists() else "missing"
    return checksums


def _workspace_path(path_text: Any) -> Path | None:
    if path_text is None:
        return None
    path = Path(str(path_text))
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _same_checkpoint_file(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    if str(left) == str(right):
        return True
    left_path = _workspace_path(left)
    right_path = _workspace_path(right)
    if left_path is None or right_path is None:
        return False
    if not left_path.exists() or not right_path.exists():
        return False
    return _sha256(left_path) == _sha256(right_path)


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _rowcorr_count(rowcorr: dict[str, Any], singular_key: str, plural_key: str) -> Any:
    value = rowcorr.get(singular_key)
    if value is not None:
        return value
    values = _as_list(rowcorr.get(plural_key))
    return values[-1] if values else None


def _first_int(value: Any) -> int | None:
    values = _as_list(value)
    candidate = values[0] if values else value
    try:
        return int(candidate)
    except (TypeError, ValueError):
        return None


def _direct_final_residual(payload: dict[str, Any]) -> float | None:
    final_group = _as_dict(payload.get("final_direct_residual"))
    return _float_or_none(
        payload.get("final_direct_residual_inf_n")
        if payload.get("final_direct_residual_inf_n") is not None
        else final_group.get("direct_residual_inf_n")
    )


def _direct_base_residual(payload: dict[str, Any]) -> float | None:
    if isinstance(payload.get("controller"), dict):
        best_candidate = _as_dict(payload.get("best_candidate_row"))
        value = _float_or_none(best_candidate.get("base_direct_residual_inf_n"))
        if value is not None:
            return value
        for row in _as_list(payload.get("promoted_rows")):
            if not isinstance(row, dict):
                continue
            value = _float_or_none(row.get("base_direct_residual_inf_n"))
            if value is not None:
                return value
        for row in _as_list(payload.get("rows")):
            if not isinstance(row, dict):
                continue
            value = _float_or_none(row.get("base_direct_residual_inf_n"))
            if value is not None:
                return value

    base_group = _as_dict(payload.get("base_direct_residual"))
    value = _float_or_none(
        payload.get("initial_frontier_direct_residual_inf_n")
        if payload.get("initial_frontier_direct_residual_inf_n") is not None
        else base_group.get("direct_residual_inf_n")
    )
    if value is not None:
        return value
    rows = [row for row in _as_list(payload.get("rows")) if isinstance(row, dict)]
    for row in rows:
        value = _float_or_none(row.get("base_direct_residual_inf_n"))
        if value is not None:
            return value
    return None


def _compact_checkpoint(path: Path, payload: dict[str, Any]) -> tuple[str | None, bool | None]:
    checkpoint_path = payload.get("final_checkpoint_path")
    output_checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    if checkpoint_path is None:
        checkpoint_path = output_checkpoint.get("path")
    if checkpoint_path is None:
        return None, None
    checkpoint_text = str(checkpoint_path)
    checkpoint = Path(checkpoint_text)
    if not checkpoint.is_absolute():
        checkpoint = Path.cwd() / checkpoint
    return checkpoint_text, checkpoint.exists()


def _checkpoint_compact_claim(payload: dict[str, Any], checkpoint_text: str | None) -> bool | None:
    output_checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    if output_checkpoint.get("compact_checkpoint") is not None:
        return bool(output_checkpoint.get("compact_checkpoint"))
    controller = _as_dict(payload.get("controller"))
    if controller.get("compact_output_final_checkpoint") is not None:
        return bool(controller.get("compact_output_final_checkpoint"))
    if controller.get("compact_child_checkpoints") is not None:
        return bool(controller.get("compact_child_checkpoints"))
    if checkpoint_text is not None and "compact" in Path(str(checkpoint_text)).name:
        return True
    if (
        checkpoint_text is not None
        and payload.get("schema_version")
        == "mgt-direct-residual-adaptive-preconditioned-global-newton.v1"
    ):
        return False
    return None


def _controller_row_summary(payload: dict[str, Any]) -> dict[str, Any]:
    controller = _as_dict(payload.get("controller"))
    rows = [row for row in _as_list(payload.get("rows")) if isinstance(row, dict)]
    promoted_rows = [
        row for row in _as_list(payload.get("promoted_rows")) if isinstance(row, dict)
    ]
    internal_pass_finals: list[float] = []
    for row in promoted_rows or rows:
        child_path = row.get("child_receipt_path")
        if not child_path:
            continue
        child = _load_json_dict(Path(str(child_path)))
        for promotion in _as_list(child.get("promotion_passes")):
            if not isinstance(promotion, dict):
                continue
            value = _float_or_none(promotion.get("actual_direct_residual_inf_n"))
            if value is not None:
                internal_pass_finals.append(value)
        rowcorr = _as_dict(child.get("current_tangent_residual_row_correction"))
        for promotion in _as_list(rowcorr.get("passes")):
            if not isinstance(promotion, dict):
                continue
            best_candidate = _as_dict(promotion.get("best_candidate"))
            value = _float_or_none(best_candidate.get("direct_residual_inf_n"))
            if value is not None:
                internal_pass_finals.append(value)
    return {
        "promotion_count": controller.get("promotion_count"),
        "max_row_promotions": controller.get("max_row_promotions_per_child"),
        "stop_reason": controller.get("stop_reason"),
        "runtime_budget_exceeded": controller.get("runtime_budget_exceeded"),
        "row_count": len(rows),
        "promoted_row_count": len(promoted_rows),
        "internal_pass_finals_n": internal_pass_finals,
    }


def _frontier_row(productization_dir: Path, receipt: str) -> dict[str, Any]:
    path = productization_dir / receipt
    payload = _load_json_dict(path)
    final_residual = _direct_final_residual(payload)
    base_residual = _direct_base_residual(payload)
    compact_checkpoint, compact_checkpoint_exists = _compact_checkpoint(path, payload)
    checkpoint_compact = _checkpoint_compact_claim(payload, compact_checkpoint)
    rowcorr = _as_dict(payload.get("current_tangent_residual_row_correction"))
    controller_summary = _controller_row_summary(payload)
    return {
        "receipt": receipt,
        "path": str(path),
        "available": bool(payload),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "base_direct_residual_inf_n": base_residual,
        "direct_residual_inf_n": final_residual,
        "target_row_count": _rowcorr_count(
            rowcorr, "target_row_count", "target_row_counts"
        ),
        "current_tangent_residual_row_target_mode": (
            rowcorr.get("target_mode")
            if rowcorr.get("target_mode") is not None
            else ("largest_rows" if rowcorr else None)
        ),
        "current_tangent_residual_row_jacobian_mode": rowcorr.get("jacobian_mode"),
        "current_tangent_residual_row_support_selection": rowcorr.get(
            "support_selection"
        ),
        "support_column_count": _rowcorr_count(
            rowcorr, "support_column_count", "support_column_counts"
        ),
        "row_correction_accepted": _bool_or_none(rowcorr.get("accepted")),
        "row_correction_promotion_count": rowcorr.get("promotion_count"),
        "row_correction_stop_reason": rowcorr.get("stop_reason"),
        "controller": controller_summary,
        "final_checkpoint_path": compact_checkpoint,
        "compact_checkpoint": compact_checkpoint,
        "compact_checkpoint_exists": compact_checkpoint_exists,
        "checkpoint_compact": checkpoint_compact,
    }


def _counter_row(productization_dir: Path, receipt: str) -> dict[str, Any]:
    path = productization_dir / receipt
    payload = _load_json_dict(path)
    return {
        "receipt": receipt,
        "path": str(path),
        "available": bool(payload),
        "status": payload.get("status"),
        "direct_residual_inf_n": _direct_final_residual(payload),
        "result": (
            "support8_replay_matched_seed_frontier"
            if receipt.endswith("followup382_support8_checkpointed.json")
            else "counter_evidence"
        ),
    }


def _launch_row(productization_dir: Path, receipt: str) -> dict[str, Any]:
    path = productization_dir / receipt
    payload = _load_json_dict(path)
    controller = _as_dict(payload.get("controller"))
    strict_hip_runtime_preflight = _as_dict(controller.get("strict_hip_runtime_preflight"))
    final_residual = _direct_final_residual(payload)
    rows = [row for row in _as_list(payload.get("rows")) if isinstance(row, dict)]
    child_base_residuals = [
        value
        for value in (_float_or_none(row.get("base_direct_residual_inf_n")) for row in rows)
        if value is not None
    ]
    child_final_residuals = [
        value
        for value in (_float_or_none(row.get("final_direct_residual_inf_n")) for row in rows)
        if value is not None
    ]
    child_stop_reasons = [
        row.get("row_correction_stop_reason")
        for row in rows
        if row.get("row_correction_stop_reason")
    ]
    child_target_counts = [
        value
        for value in (_first_int(row.get("target_row_count")) for row in rows)
        if value is not None
    ]
    child_support_counts = [
        value
        for value in (_first_int(row.get("support_column_count")) for row in rows)
        if value is not None
    ]
    child_best_final = min(child_final_residuals) if child_final_residuals else None
    top_level_child_frontier_mismatch = (
        final_residual is not None
        and child_best_final is not None
        and abs(final_residual - child_best_final) > 1.0e-12
    )
    return {
        "receipt": receipt,
        "path": str(path),
        "available": bool(payload),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "direct_residual_inf_n": (
            child_best_final if child_best_final is not None else final_residual
        ),
        "top_level_direct_residual_inf_n": final_residual,
        "top_level_child_frontier_mismatch": top_level_child_frontier_mismatch,
        "top_level_direct_residual_counted": not top_level_child_frontier_mismatch,
        "top_level_residual_boundary": (
            "top_level_controller_residual_differs_from_child_frontier; "
            "status uses child receipt residual for non-promoting boundary evidence"
            if top_level_child_frontier_mismatch
            else ""
        ),
        "final_checkpoint_path": payload.get("final_checkpoint_path"),
        "controller_promotion_count": controller.get("promotion_count"),
        "controller_stop_reason": controller.get("stop_reason"),
        "controller_row_target_mode": (
            controller.get("row_target_mode")
            if controller.get("row_target_mode") is not None
            else ("largest_rows" if controller else None)
        ),
        "controller_row_jacobian_mode": controller.get("row_jacobian_mode"),
        "controller_row_support_selection": controller.get("row_support_selection"),
        "controller_row_target_counts": (
            controller.get("row_target_counts") or child_target_counts or None
        ),
        "controller_row_support_column_counts": (
            controller.get("row_support_column_counts") or child_support_counts or None
        ),
        "runtime_budget_exceeded": controller.get("runtime_budget_exceeded"),
        "child_attempt_count": len(rows),
        "child_accepted_count": sum(1 for row in rows if row.get("accepted") is True),
        "child_best_base_direct_residual_inf_n": (
            min(child_base_residuals) if child_base_residuals else None
        ),
        "child_best_final_direct_residual_inf_n": (
            child_best_final
        ),
        "child_row_correction_stop_reasons": child_stop_reasons,
        "strict_hip_runtime_preflight": strict_hip_runtime_preflight or None,
        "strict_hip_runtime_available": strict_hip_runtime_preflight.get("available"),
        "claim_boundary": payload.get("claim_boundary"),
        "counted_in_frontier": False,
        "non_count_reason": (
            "completed frontier-promoting child direct-residual receipt required"
            if payload
            else "receipt_missing"
        ),
    }


def _pending_launch_only_row(productization_dir: Path, receipt: str) -> dict[str, Any]:
    path = productization_dir / receipt
    payload = _load_json_dict(path)
    return {
        "receipt": receipt,
        "path": str(path),
        "available": bool(payload),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "checkpoint": payload.get("checkpoint"),
        "output_json": payload.get("output_json"),
        "output_final_checkpoint_npz": payload.get("output_final_checkpoint_npz"),
        "row_target_mode": payload.get("row_target_mode"),
        "row_jacobian_mode": payload.get("row_jacobian_mode"),
        "row_support_selection": payload.get("row_support_selection"),
        "target_row_count": payload.get("target_row_count"),
        "support_column_count": payload.get("support_column_count"),
        "child_timeout_seconds": payload.get("child_timeout_seconds"),
        "claim_boundary": payload.get("claim_boundary"),
        "counted_in_frontier": False,
        "non_count_reason": (
            "completed child direct-residual receipt required before residual progress can be claimed"
            if payload
            else "receipt_missing"
        ),
    }


def _duplicate_alias_row(
    productization_dir: Path, receipt: str, duplicate_of: str
) -> dict[str, Any]:
    row = _launch_row(productization_dir, receipt)
    canonical_payload = _load_json_dict(productization_dir / duplicate_of)
    row.update(
        {
            "duplicate_of_receipt": duplicate_of,
            "duplicate_of_available": bool(canonical_payload),
            "counted_in_frontier": False,
            "counted_in_row_target_exhaustion": False,
            "non_count_reason": (
                "duplicate alias of canonical non-promoting receipt; retained for "
                "traceability only"
                if row.get("available")
                else "receipt_missing"
            ),
            "claim_boundary": {
                "duplicate_alias_only": True,
                "canonical_receipt": duplicate_of,
                "does_not_claim_independent_descent": True,
                "does_not_claim_additional_row_mode_exhaustion": True,
                "does_not_claim_g1_closure": True,
                "source_claim_boundary": row.get("claim_boundary"),
            },
        }
    )
    return row


def _hip_residual_row_backend_row(productization_dir: Path, receipt: str) -> dict[str, Any]:
    path = productization_dir / receipt
    payload = _load_json_dict(path)
    result = _as_dict(payload.get("result"))
    cumulative = _as_dict(payload.get("cumulative"))
    cumulative_from_followup69 = _as_dict(payload.get("cumulative_from_followup69"))
    followup69_largest_rows = _as_dict(payload.get("followup69_largest_rows"))
    followup68_shell_coupled = _as_dict(payload.get("followup68_shell_coupled"))
    source_candidates = (
        result,
        cumulative,
        cumulative_from_followup69,
        followup69_largest_rows,
        followup68_shell_coupled,
    )
    source = next(
        (
            candidate
            for candidate in source_candidates
            if candidate.get("final_direct_residual_inf_n") is not None
        ),
        {},
    )
    residual_gate_n = _float_or_none(payload.get("residual_gate_n"))
    base_residual = _float_or_none(source.get("base_direct_residual_inf_n"))
    final_residual = _float_or_none(source.get("final_direct_residual_inf_n"))
    if final_residual is None:
        latest_frontier = _as_dict(payload.get("latest_frontier"))
        final_residual = _float_or_none(latest_frontier.get("base_direct_residual_inf_n"))
    residual_gate_passed = source.get("residual_gate_passed")
    if residual_gate_passed is None:
        residual_gate_passed = (
            final_residual is not None
            and residual_gate_n is not None
            and final_residual <= residual_gate_n
        )
    residual_gate_passed = bool(residual_gate_passed)
    claim_boundary = str(payload.get("claim_boundary") or "")
    production_residency_claimed = bool(
        payload.get("contract_pass") is True
        or (
            payload.get("status") == "ready"
            and "does not claim" not in claim_boundary.lower()
            and "not claim" not in claim_boundary.lower()
        )
    )
    blocking_reasons = []
    if not payload:
        blocking_reasons.append("receipt_missing")
    if payload and not residual_gate_passed:
        blocking_reasons.append("residual_gate_not_closed")
    if payload and not production_residency_claimed:
        blocking_reasons.append("production_in_process_rocm_hip_residency_not_claimed")
    return {
        "receipt": receipt,
        "path": str(path),
        "available": bool(payload),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "base_direct_residual_inf_n": base_residual,
        "final_direct_residual_inf_n": final_residual,
        "residual_gate_n": residual_gate_n,
        "residual_gate_passed": residual_gate_passed,
        "production_residency_claimed": production_residency_claimed,
        "contract_pass": bool(residual_gate_passed and production_residency_claimed),
        "blocking_reasons": blocking_reasons,
        "claim_boundary": payload.get("claim_boundary"),
        "assessment": payload.get("assessment"),
        "next_solver_step": payload.get("next_solver_step"),
    }


def _claim_boundary_disclaims_closure(value: Any) -> bool:
    claim_boundary = str(value or "").lower()
    return any(
        phrase in claim_boundary
        for phrase in (
            "does not claim",
            "do not claim",
            "not claim",
            "not a nonlinear equilibrium closure",
            "does not close",
        )
    )


def _consistent_residual_jacobian_row(
    productization_dir: Path, receipt: str
) -> dict[str, Any]:
    path = productization_dir / receipt
    payload = _load_json_dict(path)
    followup86 = _as_dict(payload.get("followup86_hotspot_jvp_audit"))
    latest_residual_state = _as_dict(payload.get("latest_residual_state"))

    raw_ready = payload.get("residual_jacobian_consistency_ready")
    if raw_ready is None:
        raw_ready = followup86.get("residual_jacobian_consistency_ready")
    consistency_ready = bool(raw_ready)

    component_only = bool(payload.get("component_only") is True)
    blockers = [str(blocker) for blocker in _as_list(payload.get("blockers"))]
    claim_boundary = payload.get("claim_boundary")
    disclaims_closure = _claim_boundary_disclaims_closure(claim_boundary)
    base_residual = _float_or_none(
        payload.get("base_residual_inf_n")
        if payload.get("base_residual_inf_n") is not None
        else (
            latest_residual_state.get("direct_residual_inf_n")
            if latest_residual_state.get("direct_residual_inf_n") is not None
            else payload.get("latest_direct_residual_inf_n")
        )
    )
    residual_margin = _float_or_none(
        latest_residual_state.get("remaining_residual_margin_to_gate_n")
        if latest_residual_state.get("remaining_residual_margin_to_gate_n")
        is not None
        else payload.get("remaining_residual_margin_to_gate_n")
    )
    production_residency_claimed = bool(
        payload.get("production_rocm_hip_residency_claimed") is True
    )
    controller_start_checkpoint = payload.get("start_checkpoint")
    controller_start_checkpoint_path = (
        Path(str(controller_start_checkpoint)) if controller_start_checkpoint else None
    )
    controller_start_checkpoint_exists = (
        None
        if controller_start_checkpoint_path is None
        else (
            controller_start_checkpoint_path.exists()
            if controller_start_checkpoint_path.is_absolute()
            else (REPO_ROOT / controller_start_checkpoint_path).exists()
        )
    )
    latest_checkpoint = payload.get("latest_checkpoint")
    latest_checkpoint_path = Path(str(latest_checkpoint)) if latest_checkpoint else None
    latest_checkpoint_exists = (
        None
        if latest_checkpoint_path is None
        else (
            latest_checkpoint_path.exists()
            if latest_checkpoint_path.is_absolute()
                else (REPO_ROOT / latest_checkpoint_path).exists()
        )
    )
    latest_checkpoint_step = None
    for step in _as_list(payload.get("steps")):
        step = _as_dict(step)
        if step.get("checkpoint") == latest_checkpoint:
            latest_checkpoint_step = step
    latest_checkpoint_retained_by_summary = (
        None
        if latest_checkpoint_step is None
        else bool(latest_checkpoint_step.get("checkpoint_retained") is True)
    )
    latest_checkpoint_promoted_by_summary = (
        None
        if latest_checkpoint_step is None
        else bool(latest_checkpoint_step.get("promoted") is True)
    )
    advertised_retained_checkpoint_missing = bool(
        latest_checkpoint
        and latest_checkpoint_exists is False
        and latest_checkpoint_retained_by_summary is True
    )
    missing_controller_replay_artifacts: list[dict[str, Any]] = []
    seen_missing_controller_replay_artifacts: set[tuple[str, str]] = set()

    def add_missing_controller_replay_artifact(role: str, raw_path: Any) -> None:
        if not raw_path:
            return
        candidate = Path(str(raw_path))
        exists = (
            candidate.exists()
            if candidate.is_absolute()
            else (REPO_ROOT / candidate).exists()
        )
        if exists:
            return
        key = (role, str(raw_path))
        if key in seen_missing_controller_replay_artifacts:
            return
        seen_missing_controller_replay_artifacts.add(key)
        missing_controller_replay_artifacts.append(
            {
                "role": role,
                "path": str(raw_path),
            }
        )

    add_missing_controller_replay_artifact(
        "controller_start_checkpoint", controller_start_checkpoint
    )
    if latest_checkpoint_retained_by_summary is True:
        add_missing_controller_replay_artifact("retained_latest_checkpoint", latest_checkpoint)
    for step in _as_list(payload.get("steps")):
        step = _as_dict(step)
        add_missing_controller_replay_artifact("step_basis_npz", step.get("basis_npz"))

    controller_script = Path(
        "implementation/phase1/run_mgt_cached_residual_jvp_multi_ridge_controller.py"
    )
    controller_script_exists = (REPO_ROOT / controller_script).exists()
    step_basis_npz_count = sum(
        1
        for step in _as_list(payload.get("steps"))
        if _as_dict(step).get("basis_npz")
    )
    missing_step_basis_npz_count = sum(
        1
        for artifact in missing_controller_replay_artifacts
        if artifact.get("role") == "step_basis_npz"
    )
    restart_ready = bool(latest_checkpoint and latest_checkpoint_exists is True)
    can_regenerate_advertised_chain = bool(
        payload and controller_script_exists and controller_start_checkpoint_exists is True
    )
    can_replay_advertised_chain = bool(
        payload and restart_ready and not missing_controller_replay_artifacts
    )
    regeneration_feasibility_blockers = []
    if not payload:
        regeneration_feasibility_blockers.append("summary_receipt_missing")
    if payload and not controller_script_exists:
        regeneration_feasibility_blockers.append("controller_script_missing")
    if payload and controller_start_checkpoint_exists is False:
        regeneration_feasibility_blockers.append("controller_start_checkpoint_missing")
    if payload and latest_checkpoint_exists is False:
        regeneration_feasibility_blockers.append("advertised_latest_checkpoint_missing")
    if payload and missing_step_basis_npz_count:
        regeneration_feasibility_blockers.append("advertised_step_basis_npz_missing")
    if payload and advertised_retained_checkpoint_missing:
        regeneration_feasibility_blockers.append(
            "advertised_retained_checkpoint_missing"
        )
    regeneration_feasibility = {
        "schema_version": "g1-cached-residual-jvp-regeneration-feasibility.v1",
        "controller_script": str(controller_script),
        "controller_script_exists": controller_script_exists,
        "summary_receipt": receipt,
        "summary_receipt_available": bool(payload),
        "start_checkpoint": controller_start_checkpoint,
        "start_checkpoint_exists": controller_start_checkpoint_exists,
        "advertised_latest_checkpoint": latest_checkpoint,
        "advertised_latest_checkpoint_exists": latest_checkpoint_exists,
        "advertised_latest_checkpoint_retained_by_summary": (
            latest_checkpoint_retained_by_summary
        ),
        "advertised_latest_checkpoint_promoted_by_summary": (
            latest_checkpoint_promoted_by_summary
        ),
        "step_basis_npz_expected_count": step_basis_npz_count,
        "step_basis_npz_missing_count": missing_step_basis_npz_count,
        "missing_artifact_count": len(missing_controller_replay_artifacts),
        "missing_artifacts": missing_controller_replay_artifacts,
        "can_regenerate_advertised_chain": can_regenerate_advertised_chain,
        "can_replay_advertised_chain": can_replay_advertised_chain,
        "blocked_reasons": regeneration_feasibility_blockers,
        "non_promoting_regeneration_command_template": [
            "python3",
            str(controller_script),
            "--start-checkpoint-npz",
            str(controller_start_checkpoint or "<missing-start-checkpoint>"),
            "--start-followup-index",
            "<next-followup-index>",
            "--max-steps",
            "<bounded-step-count>",
            "--allow-cpu-diagnostic",
        ],
        "claim_boundary": (
            "This gate describes whether the advertised cached residual/JVP chain "
            "can be regenerated or replay-verified from present local artifacts. "
            "It is diagnostic routing evidence only and cannot close G1 without "
            "full-load, full-mesh nonlinear equilibrium, material Newton breadth, "
            "and production ROCm/HIP residency evidence."
        ),
    }

    contract_pass = bool(
        payload
        and payload.get("status") == "ready"
        and consistency_ready
        and not component_only
        and not blockers
        and residual_margin is not None
        and residual_margin <= 0.0
        and production_residency_claimed
        and restart_ready
        and not disclaims_closure
    )

    blocking_reasons = []
    if not payload:
        blocking_reasons.append("receipt_missing")
    if payload and payload.get("status") != "ready":
        blocking_reasons.append("receipt_not_ready")
    if payload and not consistency_ready:
        blocking_reasons.append("residual_jacobian_consistency_not_ready")
    if payload and component_only:
        blocking_reasons.append("component_only_diagnostic_not_consistency_closure")
    if payload and blockers:
        blocking_reasons.extend(blockers)
    if payload and (residual_margin is None or residual_margin > 0.0):
        blocking_reasons.append("residual_gate_not_closed")
    if payload and not production_residency_claimed:
        blocking_reasons.append("production_in_process_rocm_hip_residency_not_claimed")
    if payload and controller_start_checkpoint_exists is False:
        blocking_reasons.append("controller_start_checkpoint_missing")
    if payload and missing_controller_replay_artifacts:
        blocking_reasons.append("controller_replay_artifacts_missing")
    if payload and not restart_ready:
        blocking_reasons.append(
            "latest_checkpoint_missing"
            if latest_checkpoint_exists is False
            else "latest_checkpoint_not_advertised"
        )
    if payload and advertised_retained_checkpoint_missing:
        blocking_reasons.append("advertised_retained_checkpoint_missing")
    if payload and disclaims_closure:
        blocking_reasons.append("claim_boundary_disclaims_closure")

    return {
        "receipt": receipt,
        "path": str(path),
        "available": bool(payload),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "residual_jacobian_consistency_ready": consistency_ready,
        "component_only": component_only,
        "base_direct_residual_inf_n": base_residual,
        "latest_remaining_residual_margin_to_gate_n": residual_margin,
        "residual_gate_n": _float_or_none(payload.get("residual_gate_n")),
        "controller_start_checkpoint": controller_start_checkpoint,
        "controller_start_checkpoint_exists": controller_start_checkpoint_exists,
        "latest_checkpoint": latest_checkpoint,
        "latest_checkpoint_exists": latest_checkpoint_exists,
        "latest_checkpoint_retained_by_summary": latest_checkpoint_retained_by_summary,
        "latest_checkpoint_promoted_by_summary": latest_checkpoint_promoted_by_summary,
        "advertised_retained_checkpoint_missing": advertised_retained_checkpoint_missing,
        "missing_controller_replay_artifact_count": len(
            missing_controller_replay_artifacts
        ),
        "missing_controller_replay_artifacts": missing_controller_replay_artifacts,
        "restart_ready": restart_ready,
        "regeneration_feasibility": regeneration_feasibility,
        "load_scale": payload.get("load_scale"),
        "production_residency_claimed": production_residency_claimed,
        "contract_pass": contract_pass,
        "blocking_reasons": blocking_reasons,
        "claim_boundary": claim_boundary,
        "assessment": payload.get("assessment") or followup86.get("assessment"),
        "next_solver_step": payload.get("next_solver_step"),
    }


def build_report(
    *,
    productization_dir: Path = PRODUCTIZATION,
    chain_receipts: tuple[str, ...] = DEFAULT_FRONTIER_CHAIN,
    counter_receipts: tuple[str, ...] = DEFAULT_COUNTER_EVIDENCE,
    launch_receipts: tuple[str, ...] = DEFAULT_NON_PROMOTING_LAUNCH_RECEIPTS,
    pending_launch_only_receipts: tuple[
        str, ...
    ] = DEFAULT_PENDING_LAUNCH_ONLY_RECEIPTS,
    duplicate_alias_receipts: tuple[
        tuple[str, str], ...
    ] = DEFAULT_DUPLICATE_ALIAS_RECEIPTS,
    hip_residual_row_backend_receipts: tuple[
        str, ...
    ] = DEFAULT_HIP_RESIDUAL_ROW_BACKEND_RECEIPTS,
    consistent_residual_jacobian_receipts: tuple[
        str, ...
    ] = DEFAULT_CONSISTENT_RESIDUAL_JACOBIAN_RECEIPTS,
    direct_residual_tolerance_n: float = DEFAULT_DIRECT_RESIDUAL_TOLERANCE_N,
) -> dict[str, Any]:
    frontier_chain = [_frontier_row(productization_dir, receipt) for receipt in chain_receipts]
    counter_evidence = [_counter_row(productization_dir, receipt) for receipt in counter_receipts]
    non_promoting_launch_receipts = [
        _launch_row(productization_dir, receipt) for receipt in launch_receipts
    ]
    pending_launch_only_receipts_rows = [
        _pending_launch_only_row(productization_dir, receipt)
        for receipt in pending_launch_only_receipts
    ]
    duplicate_alias_receipts_rows = [
        _duplicate_alias_row(productization_dir, receipt, duplicate_of)
        for receipt, duplicate_of in duplicate_alias_receipts
    ]
    hip_residual_row_backend_receipts_rows = [
        _hip_residual_row_backend_row(productization_dir, receipt)
        for receipt in hip_residual_row_backend_receipts
    ]
    consistent_residual_jacobian_rows = [
        _consistent_residual_jacobian_row(productization_dir, receipt)
        for receipt in consistent_residual_jacobian_receipts
    ]
    available_hip_rows = [
        row for row in hip_residual_row_backend_receipts_rows if row.get("available")
    ]
    latest_hip_row = available_hip_rows[-1] if available_hip_rows else {}
    latest_hip_residual = _float_or_none(
        latest_hip_row.get("final_direct_residual_inf_n")
    )
    latest_hip_gate = _float_or_none(latest_hip_row.get("residual_gate_n"))
    hip_backend_contract_pass = bool(
        latest_hip_row and latest_hip_row.get("contract_pass") is True
    )
    available_consistent_jacobian_rows = [
        row for row in consistent_residual_jacobian_rows if row.get("available")
    ]
    latest_consistent_jacobian_row = (
        available_consistent_jacobian_rows[-1]
        if available_consistent_jacobian_rows
        else {}
    )
    consistent_jacobian_contract_pass = bool(
        latest_consistent_jacobian_row
        and latest_consistent_jacobian_row.get("contract_pass") is True
    )
    latest_consistent_jacobian_checkpoint = latest_consistent_jacobian_row.get(
        "latest_checkpoint"
    )
    latest_consistent_jacobian_checkpoint_exists = latest_consistent_jacobian_row.get(
        "latest_checkpoint_exists"
    )
    consistent_jacobian_restart_ready = bool(
        latest_consistent_jacobian_row
        and latest_consistent_jacobian_row.get("restart_ready") is True
    )
    consistent_jacobian_restart_blockers = []
    if latest_consistent_jacobian_row and not consistent_jacobian_restart_ready:
        consistent_jacobian_restart_blockers.append(
            "latest_checkpoint_missing"
            if latest_consistent_jacobian_checkpoint_exists is False
            else "latest_checkpoint_not_advertised"
        )
        if latest_consistent_jacobian_row.get(
            "advertised_retained_checkpoint_missing"
        ):
            consistent_jacobian_restart_blockers.append(
                "advertised_retained_checkpoint_missing"
            )
        if latest_consistent_jacobian_row.get(
            "controller_start_checkpoint_exists"
        ) is False:
            consistent_jacobian_restart_blockers.append(
                "controller_start_checkpoint_missing"
            )
        if latest_consistent_jacobian_row.get(
            "missing_controller_replay_artifact_count"
        ):
            consistent_jacobian_restart_blockers.append(
                "controller_replay_artifacts_missing"
            )

    residuals = [
        row.get("direct_residual_inf_n")
        for row in frontier_chain
        if row.get("direct_residual_inf_n") is not None
    ]
    latest_residual = residuals[-1] if residuals else None
    first_residual = residuals[0] if residuals else None
    latest_frontier_row = frontier_chain[-1] if frontier_chain else {}
    latest_frontier_receipt = str(latest_frontier_row.get("receipt") or "")
    latest_frontier_checkpoint = latest_frontier_row.get("compact_checkpoint")
    latest_frontier_checkpoint_exists = latest_frontier_row.get(
        "compact_checkpoint_exists"
    )
    latest_frontier_checkpoint_compact = latest_frontier_row.get("checkpoint_compact")
    checkpoint_compact_values = [
        row.get("checkpoint_compact")
        for row in frontier_chain
        if row.get("compact_checkpoint") is not None
    ]
    frontier_chain_full_history_checkpoint_present = any(
        value is False for value in checkpoint_compact_values
    )
    checkpoint_compactness_unknown_count = sum(
        1 for value in checkpoint_compact_values if value is None
    )
    monotonic_nonincreasing = all(
        float(right) <= float(left) + 1.0e-12
        for left, right in zip(residuals, residuals[1:])
    )
    missing_receipts = [row["receipt"] for row in frontier_chain if not row["available"]]
    missing_checkpoints = [
        row["receipt"]
        for row in frontier_chain
        if row.get("compact_checkpoint") and row.get("compact_checkpoint_exists") is False
    ]
    direct_residual_gate_passed = (
        latest_residual is not None and latest_residual <= direct_residual_tolerance_n
    )
    blockers = [
        *(["frontier_receipt_missing"] if missing_receipts else []),
        *(["frontier_residual_not_monotonic"] if not monotonic_nonincreasing else []),
        *(["compact_checkpoint_missing"] if missing_checkpoints else []),
        *(["direct_residual_gate_not_closed"] if not direct_residual_gate_passed else []),
        "full_mesh_nonlinear_equilibrium_not_closed",
        *(
            ["production_rocm_hip_residual_row_backend_not_closed"]
            if not hip_backend_contract_pass
            else []
        ),
        *(
            ["consistent_residual_jacobian_newton_not_closed"]
            if not consistent_jacobian_contract_pass
            else []
        ),
    ]
    improvement = (
        first_residual - latest_residual
        if first_residual is not None and latest_residual is not None
        else None
    )
    relative_improvement = (
        improvement / max(first_residual, 1.0e-30)
        if improvement is not None and first_residual is not None
        else None
    )
    residual_gap_to_tolerance_n = (
        latest_residual - direct_residual_tolerance_n
        if latest_residual is not None
        else None
    )
    residual_gap_ratio_to_tolerance = (
        latest_residual / direct_residual_tolerance_n
        if latest_residual is not None and direct_residual_tolerance_n > 0.0
        else None
    )
    checkpoint_next_action = (
        f"continue from latest compact checkpoint {latest_frontier_checkpoint} "
        f"({latest_frontier_receipt}) only through completed child receipts"
        if latest_frontier_checkpoint
        else f"continue from latest completed receipt {latest_frontier_receipt} "
        "only through completed child receipts"
    )
    same_operator_no_descent_rows_by_receipt = {
        str(row.get("receipt")): row
        for row in frontier_chain
        if row.get("row_correction_stop_reason") == "no_residual_descent"
    }
    same_operator_no_descent_rows_by_receipt.update(
        {
            str(row.get("receipt")): row
            for row in non_promoting_launch_receipts
            if row.get("child_attempt_count")
            and row.get("child_accepted_count") == 0
            and "no_residual_descent" in _as_list(row.get("child_row_correction_stop_reasons"))
        }
    )
    same_operator_no_descent_rows = [
        row
        for row in (
            *non_promoting_launch_receipts,
            *frontier_chain,
        )
        if str(row.get("receipt")) in same_operator_no_descent_rows_by_receipt
    ]
    latest_frontier_operator_no_descent = (
        latest_frontier_row.get("row_correction_stop_reason") == "no_residual_descent"
    )
    same_operator_repetition_exhausted = bool(
        same_operator_no_descent_rows or latest_frontier_operator_no_descent
    )
    same_operator_exhausted_at_latest_checkpoint = any(
        _same_checkpoint_file(row.get("final_checkpoint_path"), latest_frontier_checkpoint)
        for row in same_operator_no_descent_rows
    ) or latest_frontier_operator_no_descent
    row_target_mode_no_descent_receipts_at_latest_checkpoint: dict[str, str] = {}
    for row in same_operator_no_descent_rows:
        mode = row.get("controller_row_target_mode")
        if not mode:
            continue
        if not _same_checkpoint_file(row.get("final_checkpoint_path"), latest_frontier_checkpoint):
            continue
        if row.get("counted_in_frontier") is False:
            row_target_mode_no_descent_receipts_at_latest_checkpoint[
                str(mode)
            ] = str(row.get("receipt"))
        else:
            row_target_mode_no_descent_receipts_at_latest_checkpoint.setdefault(
                str(mode), str(row.get("receipt"))
            )
    latest_mode = latest_frontier_row.get("current_tangent_residual_row_target_mode")
    if latest_frontier_operator_no_descent and latest_mode:
        row_target_mode_no_descent_receipts_at_latest_checkpoint.setdefault(
            str(latest_mode), latest_frontier_receipt
        )
    exhausted_row_target_modes = [
        mode
        for mode in DEFAULT_ROW_TARGET_MODES
        if mode in row_target_mode_no_descent_receipts_at_latest_checkpoint
    ]
    missing_row_target_modes = [
        mode
        for mode in DEFAULT_ROW_TARGET_MODES
        if mode not in row_target_mode_no_descent_receipts_at_latest_checkpoint
    ]
    all_row_target_modes_exhausted_at_latest_checkpoint = not missing_row_target_modes
    largest_rows_strategy_no_descent_receipts_at_latest_checkpoint: dict[str, str] = {}
    largest_rows_strategy_candidates = [*same_operator_no_descent_rows]
    if latest_frontier_operator_no_descent:
        largest_rows_strategy_candidates.append(latest_frontier_row)
    for row in largest_rows_strategy_candidates:
        if not _same_checkpoint_file(row.get("final_checkpoint_path"), latest_frontier_checkpoint):
            continue
        mode = (
            row.get("controller_row_target_mode")
            or row.get("current_tangent_residual_row_target_mode")
        )
        if mode != "largest_rows":
            continue
        target_count = (
            _first_int(row.get("controller_row_target_counts"))
            or _first_int(row.get("target_row_count"))
        )
        support_count = (
            _first_int(row.get("controller_row_support_column_counts"))
            or _first_int(row.get("support_column_count"))
        )
        support_selection = (
            row.get("controller_row_support_selection")
            or row.get("current_tangent_residual_row_support_selection")
            or "row_strongest"
        )
        jacobian_mode = (
            row.get("controller_row_jacobian_mode")
            or row.get("current_tangent_residual_row_jacobian_mode")
            or "current_tangent"
        )
        for strategy in DEFAULT_LARGEST_ROWS_OPERATOR_STRATEGIES:
            if (
                strategy["row_target_mode"] == mode
                and strategy["row_support_selection"] == support_selection
                and strategy["row_jacobian_mode"] == jacobian_mode
                and strategy["target_row_count"] == target_count
                and strategy["support_column_count"] == support_count
            ):
                largest_rows_strategy_no_descent_receipts_at_latest_checkpoint[
                    str(strategy["id"])
                ] = str(row.get("receipt"))
    exhausted_largest_rows_strategy_ids = [
        str(strategy["id"])
        for strategy in DEFAULT_LARGEST_ROWS_OPERATOR_STRATEGIES
        if str(strategy["id"])
        in largest_rows_strategy_no_descent_receipts_at_latest_checkpoint
    ]
    missing_largest_rows_strategy_ids = [
        str(strategy["id"])
        for strategy in DEFAULT_LARGEST_ROWS_OPERATOR_STRATEGIES
        if str(strategy["id"])
        not in largest_rows_strategy_no_descent_receipts_at_latest_checkpoint
    ]
    all_largest_rows_strategies_exhausted_at_latest_checkpoint = (
        not missing_largest_rows_strategy_ids
    )
    if same_operator_exhausted_at_latest_checkpoint:
        exhausted_receipt_names = [
            str(row.get("receipt")) for row in same_operator_no_descent_rows
        ]
        if (
            latest_frontier_operator_no_descent
            and latest_frontier_receipt
            not in exhausted_receipt_names
        ):
            exhausted_receipt_names.append(latest_frontier_receipt)
        exhausted_receipts = ", ".join(exhausted_receipt_names)
        checkpoint_next_action = (
            "do not repeat the same target/support row-correction operator from "
            f"{latest_frontier_checkpoint or latest_frontier_receipt}; "
            f"latest non-promoting no-descent receipt(s): {exhausted_receipts}. "
            "Use a changed row target/support/operator, a consistent residual/Jacobian "
            "Newton path, or the production ROCm/HIP lane."
        )
    if all_row_target_modes_exhausted_at_latest_checkpoint:
        checkpoint_next_action = (
            "all configured row target modes are exhausted at the latest checkpoint; "
            "do not spend another slice on plain row-target retuning. Use a "
            "consistent residual/Jacobian Newton path, a production ROCm/HIP "
            "residual/JVP worker, or a different coupled operator/preconditioner."
        )
    if all_largest_rows_strategies_exhausted_at_latest_checkpoint:
        checkpoint_next_action = (
            "all configured largest-rows target128/support8 support/Jacobian "
            "strategies are exhausted at the latest checkpoint; do not spend "
            "another slice on largest-rows support/Jacobian retuning. Use a "
            "consistent residual/Jacobian Newton path, a production ROCm/HIP "
            "residual/JVP worker, or a different coupled operator/preconditioner."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "input_checksums": _input_checksums(
            [
                *[productization_dir / receipt for receipt in chain_receipts],
                *[productization_dir / receipt for receipt in counter_receipts],
                *[productization_dir / receipt for receipt in launch_receipts],
                *[productization_dir / receipt for receipt in pending_launch_only_receipts],
                *[
                    productization_dir / receipt
                    for receipt, _duplicate_of in duplicate_alias_receipts
                ],
                *[
                    productization_dir / receipt
                    for receipt in hip_residual_row_backend_receipts
                ],
                *[
                    productization_dir / receipt
                    for receipt in consistent_residual_jacobian_receipts
                ],
            ]
        ),
        "reused_evidence": True,
        "reuse_policy": (
            "status_rebuilt_from_existing_g1_shell_material_direct_residual_receipts"
        ),
        "status": "partial",
        "contract_pass": direct_residual_gate_passed,
        "target_model": "midas_generator_33.optimized.roundtrip.json",
        "direct_residual_gate_tolerance_n": direct_residual_tolerance_n,
        "direct_residual_gate_passed": direct_residual_gate_passed,
        "compact_checkpoint_ready": not missing_checkpoints,
        "shell_material_tangent_applied": True,
        "budgeted_controller_ready": True,
        "frontier_chain_monotonic_nonincreasing": monotonic_nonincreasing,
        "latest_frontier_receipt": latest_frontier_receipt,
        "latest_frontier_compact_checkpoint": latest_frontier_checkpoint,
        "latest_frontier_compact_checkpoint_exists": latest_frontier_checkpoint_exists,
        "latest_frontier_checkpoint_compact": latest_frontier_checkpoint_compact,
        "latest_frontier_direct_residual_inf_n": latest_residual,
        "residual_gap_to_tolerance_n": residual_gap_to_tolerance_n,
        "residual_gap_ratio_to_tolerance": residual_gap_ratio_to_tolerance,
        "frontier_improvement_inf_n": improvement,
        "frontier_relative_improvement": relative_improvement,
        "frontier_chain": frontier_chain,
        "counter_evidence": counter_evidence,
        "non_promoting_launch_receipts": non_promoting_launch_receipts,
        "pending_launch_only_receipts": pending_launch_only_receipts_rows,
        "duplicate_alias_receipts": duplicate_alias_receipts_rows,
        "hip_residual_row_backend": {
            "contract_pass": hip_backend_contract_pass,
            "latest_receipt": latest_hip_row.get("receipt"),
            "latest_final_direct_residual_inf_n": latest_hip_residual,
            "latest_residual_gate_n": latest_hip_gate,
            "latest_residual_gap_to_gate_n": (
                latest_hip_residual - latest_hip_gate
                if latest_hip_residual is not None and latest_hip_gate is not None
                else None
            ),
            "latest_residual_gap_ratio_to_gate": (
                latest_hip_residual / latest_hip_gate
                if latest_hip_residual is not None
                and latest_hip_gate is not None
                and latest_hip_gate > 0.0
                else None
            ),
            "claim_boundary": (
                "HIP row backend receipts are live descent/saturation evidence only; "
                "they do not close G1 unless residual gates and production in-process "
                "ROCm/HIP residency are both proven."
            ),
            "receipts": hip_residual_row_backend_receipts_rows,
        },
        "consistent_residual_jacobian_newton": {
            "contract_pass": consistent_jacobian_contract_pass,
            "latest_receipt": latest_consistent_jacobian_row.get("receipt"),
            "latest_status": latest_consistent_jacobian_row.get("status"),
            "latest_residual_jacobian_consistency_ready": (
                latest_consistent_jacobian_row.get(
                    "residual_jacobian_consistency_ready"
                )
            ),
            "latest_component_only": latest_consistent_jacobian_row.get(
                "component_only"
            ),
            "latest_remaining_residual_margin_to_gate_n": (
                latest_consistent_jacobian_row.get(
                    "latest_remaining_residual_margin_to_gate_n"
                )
            ),
            "latest_checkpoint": latest_consistent_jacobian_checkpoint,
            "latest_checkpoint_exists": latest_consistent_jacobian_checkpoint_exists,
            "controller_start_checkpoint": (
                latest_consistent_jacobian_row.get("controller_start_checkpoint")
            ),
            "controller_start_checkpoint_exists": (
                latest_consistent_jacobian_row.get(
                    "controller_start_checkpoint_exists"
                )
            ),
            "latest_checkpoint_retained_by_summary": (
                latest_consistent_jacobian_row.get(
                    "latest_checkpoint_retained_by_summary"
                )
            ),
            "latest_checkpoint_promoted_by_summary": (
                latest_consistent_jacobian_row.get(
                    "latest_checkpoint_promoted_by_summary"
                )
            ),
            "advertised_retained_checkpoint_missing": (
                latest_consistent_jacobian_row.get(
                    "advertised_retained_checkpoint_missing"
                )
            ),
            "missing_controller_replay_artifact_count": (
                latest_consistent_jacobian_row.get(
                    "missing_controller_replay_artifact_count"
                )
            ),
            "missing_controller_replay_artifacts": (
                latest_consistent_jacobian_row.get(
                    "missing_controller_replay_artifacts"
                )
            ),
            "restart_ready": consistent_jacobian_restart_ready,
            "restart_blockers": consistent_jacobian_restart_blockers,
            "regeneration_feasibility": latest_consistent_jacobian_row.get(
                "regeneration_feasibility"
            ),
            "claim_boundary": (
                "Residual/Jacobian receipts are diagnostic evidence until they prove "
                "a production ROCm/HIP, non-component-only Newton path with residual "
                "gate closure, a present restart checkpoint, and no closure-disclaiming "
                "claim boundary."
            ),
            "receipts": consistent_residual_jacobian_rows,
        },
        "same_operator_repetition_exhausted": same_operator_repetition_exhausted,
        "same_operator_exhausted_at_latest_checkpoint": (
            same_operator_exhausted_at_latest_checkpoint
        ),
        "same_operator_no_descent_receipts": [
            *(row.get("receipt") for row in same_operator_no_descent_rows),
            *(
                [latest_frontier_receipt]
                if latest_frontier_operator_no_descent
                and latest_frontier_receipt
                not in {str(row.get("receipt")) for row in same_operator_no_descent_rows}
                else []
            ),
        ],
        "row_target_mode_exhaustion": {
            "all_configured_modes_exhausted_at_latest_checkpoint": (
                all_row_target_modes_exhausted_at_latest_checkpoint
            ),
            "configured_modes": list(DEFAULT_ROW_TARGET_MODES),
            "exhausted_modes": exhausted_row_target_modes,
            "missing_modes": missing_row_target_modes,
            "receipt_by_mode": row_target_mode_no_descent_receipts_at_latest_checkpoint,
            "claim_boundary": (
                "This exhausts plain row target mode retuning at the latest checkpoint "
                "only. It does not close G1 and does not rule out a different "
                "consistent residual/Jacobian Newton operator or production ROCm/HIP path."
            ),
        },
        "largest_rows_operator_strategy_exhaustion": {
            "all_configured_strategies_exhausted_at_latest_checkpoint": (
                all_largest_rows_strategies_exhausted_at_latest_checkpoint
            ),
            "configured_strategies": list(DEFAULT_LARGEST_ROWS_OPERATOR_STRATEGIES),
            "exhausted_strategy_ids": exhausted_largest_rows_strategy_ids,
            "missing_strategy_ids": missing_largest_rows_strategy_ids,
            "receipt_by_strategy_id": (
                largest_rows_strategy_no_descent_receipts_at_latest_checkpoint
            ),
            "claim_boundary": (
                "This exhausts only the configured largest-rows target128/support8 "
                "support-selection/Jacobian strategy matrix at the latest checkpoint. "
                "It does not close G1 and does not rule out a different consistent "
                "residual/Jacobian Newton operator or production ROCm/HIP path."
            ),
        },
        "latest_frontier_operator_stop_reason": latest_frontier_row.get(
            "row_correction_stop_reason"
        ),
        "latest_frontier_operator_target_row_count": latest_frontier_row.get(
            "target_row_count"
        ),
        "latest_frontier_operator_support_column_count": latest_frontier_row.get(
            "support_column_count"
        ),
        "latest_frontier_operator_promotion_count": latest_frontier_row.get(
            "row_correction_promotion_count"
        ),
        "storage_policy": {
            "full_history_checkpoint_avoided": (
                not frontier_chain_full_history_checkpoint_present
            ),
            "latest_frontier_checkpoint_compact": latest_frontier_checkpoint_compact,
            "frontier_chain_full_history_checkpoint_present": (
                frontier_chain_full_history_checkpoint_present
            ),
            "checkpoint_compactness_unknown_count": checkpoint_compactness_unknown_count,
            "compact_checkpoint_contents": [
                "displacement_u",
                "load_scale",
                "direct_residual_inf_n",
                "max_translation_m",
                "source_checkpoint_path",
            ],
        },
        "blockers": blockers,
        "summary_line": (
            "G1 shell-material budgeted continuation: PARTIAL | "
            f"frontier={latest_residual} N | "
            f"gate={direct_residual_tolerance_n} N | "
            f"latest={frontier_chain[-1]['receipt'] if frontier_chain else 'none'}"
        ),
        "claim_boundary": {
            "full_mesh_nonlinear_equilibrium_closed": False,
            "direct_residual_newton_closed": False,
            "equilibrium_newton_closed": False,
            "cpu_diagnostic_only": True,
            "official_rocm_hip_closure_required": True,
            "launch_only_receipts_do_not_claim_descent": True,
            "pending_launch_only_receipts_do_not_claim_descent": True,
        },
        "next_actions": [
            checkpoint_next_action,
            "port residual-row batch replay with state-dependent shell material tangent to the production ROCm/HIP lane",
            "replace row-only correction with a consistent residual/Jacobian Newton path before claiming commercial closure",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(productization_dir=args.productization_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.json
        else payload["summary_line"]
    )
    return 1 if args.fail_blocked and payload["direct_residual_gate_passed"] is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
