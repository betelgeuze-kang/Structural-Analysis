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
)
DEFAULT_COUNTER_EVIDENCE = (
    "mgt_shell_material_rowcorr_budget_controller_followup382_support8_checkpointed.json",
)
DEFAULT_NON_PROMOTING_LAUNCH_RECEIPTS = (
    "mgt_shell_material_rowcorr_budget_controller_followup390_multistep_target4_support4_children/"
    "mgt_shell_material_rowcorr_budget_controller_followup390_multistep_target4_support4_candidate1_target4_support4.json",
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


def _direct_final_residual(payload: dict[str, Any]) -> float | None:
    final_group = _as_dict(payload.get("final_direct_residual"))
    return _float_or_none(
        payload.get("final_direct_residual_inf_n")
        if payload.get("final_direct_residual_inf_n") is not None
        else final_group.get("direct_residual_inf_n")
    )


def _direct_base_residual(payload: dict[str, Any]) -> float | None:
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
        "target_row_count": rowcorr.get("target_row_count"),
        "support_column_count": rowcorr.get("support_column_count"),
        "row_correction_accepted": _bool_or_none(rowcorr.get("accepted")),
        "row_correction_promotion_count": rowcorr.get("promotion_count"),
        "controller": controller_summary,
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
    return {
        "receipt": receipt,
        "path": str(path),
        "available": bool(payload),
        "status": payload.get("status"),
        "claim_boundary": payload.get("claim_boundary"),
        "counted_in_frontier": False,
        "non_count_reason": (
            "completed child direct-residual receipt required"
            if payload
            else "receipt_missing"
        ),
    }


def build_report(
    *,
    productization_dir: Path = PRODUCTIZATION,
    chain_receipts: tuple[str, ...] = DEFAULT_FRONTIER_CHAIN,
    counter_receipts: tuple[str, ...] = DEFAULT_COUNTER_EVIDENCE,
    launch_receipts: tuple[str, ...] = DEFAULT_NON_PROMOTING_LAUNCH_RECEIPTS,
    direct_residual_tolerance_n: float = DEFAULT_DIRECT_RESIDUAL_TOLERANCE_N,
) -> dict[str, Any]:
    frontier_chain = [_frontier_row(productization_dir, receipt) for receipt in chain_receipts]
    counter_evidence = [_counter_row(productization_dir, receipt) for receipt in counter_receipts]
    non_promoting_launch_receipts = [
        _launch_row(productization_dir, receipt) for receipt in launch_receipts
    ]

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
        "production_rocm_hip_residual_row_backend_not_closed",
        "consistent_residual_jacobian_newton_not_closed",
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
