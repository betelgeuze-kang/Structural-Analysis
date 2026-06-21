#!/usr/bin/env python3
"""Budgeted alternating G1 controller for row-FD and global Krylov Newton lanes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_mgt_direct_residual_newton_probe import DEFAULT_MGT, PRODUCTIZATION


SCHEMA_VERSION = "mgt-g1-alternating-newton-controller.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PRODUCTIZATION / "mgt_g1_alternating_newton_controller.json"


def _parse_float_csv(text: str) -> tuple[float, ...]:
    return tuple(float(value.strip()) for value in str(text).split(",") if value.strip())


def _parse_int_csv(text: str) -> tuple[int, ...]:
    return tuple(int(value.strip()) for value in str(text).split(",") if value.strip())


def _parse_lane_sequence(text: str) -> tuple[str, ...]:
    aliases = {
        "row": "row_fd_component",
        "row_fd": "row_fd_component",
        "row_fd_component": "row_fd_component",
        "global": "global_krylov",
        "krylov": "global_krylov",
        "global_krylov": "global_krylov",
    }
    lanes: list[str] = []
    for raw in str(text).split(","):
        key = raw.strip().lower()
        if not key:
            continue
        lane = aliases.get(key)
        if lane is None:
            raise ValueError(f"unsupported lane in sequence: {raw}")
        lanes.append(lane)
    return tuple(lanes)


def _csv(values: tuple[float, ...] | tuple[int, ...]) -> str:
    return ",".join(str(value) for value in values)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _residual_from_payload(payload: dict[str, Any]) -> float | None:
    if payload.get("final_direct_residual_inf_n") is not None:
        return float(payload["final_direct_residual_inf_n"])
    final = payload.get("final_direct_residual")
    if isinstance(final, dict) and final.get("direct_residual_inf_n") is not None:
        return float(final["direct_residual_inf_n"])
    return None


def _promotion_count(payload: dict[str, Any]) -> int:
    controller = payload.get("controller")
    if isinstance(controller, dict):
        return int(controller.get("promotion_count") or 0)
    rowcorr = payload.get("current_tangent_residual_row_correction")
    if isinstance(rowcorr, dict):
        return int(rowcorr.get("promotion_count") or 0)
    return 0


def _strict_fallback_zero_audit(
    payload: dict[str, Any],
    *,
    _seen_paths: set[str] | None = None,
) -> dict[str, Any]:
    _seen_paths = _seen_paths or set()
    blockers: list[dict[str, Any]] = []
    checked_receipt_count = 0

    def _add(reason: str, path: str, detail: Any = None) -> None:
        blockers.append({"reason": reason, "path": path, "detail": detail})

    def _blocker_is_strict_boundary(value: Any) -> bool:
        text = str(value)
        return any(
            token in text
            for token in (
                "fallback",
                "cpu_",
                "host_",
                "rocm_hip",
                "hip_required",
                "hip_batch_replay_required_unavailable",
                "hip_krylov_solver_required_unavailable",
            )
        )

    def _inspect(receipt: dict[str, Any], path: str) -> None:
        nonlocal checked_receipt_count
        gate = receipt.get("gate_assessment")
        if isinstance(gate, dict) and "fallback_zero_passed" in gate:
            checked_receipt_count += 1
            if gate.get("fallback_zero_passed") is not True:
                _add("fallback_zero_not_passed", path, gate.get("fallback_zero_audit"))
        controller = receipt.get("controller")
        if isinstance(controller, dict):
            preflight_blockers = controller.get("preflight_blockers")
            if isinstance(preflight_blockers, list) and preflight_blockers:
                _add("controller_preflight_blockers", path, preflight_blockers)
        claim_boundary = receipt.get("claim_boundary")
        if isinstance(claim_boundary, dict):
            if claim_boundary.get("cpu_diagnostic_only") is True:
                _add("claim_boundary_cpu_diagnostic_only", path, "cpu_diagnostic_only")
            if claim_boundary.get("official_rocm_hip_closure_required") is True:
                _add(
                    "claim_boundary_official_rocm_hip_closure_required",
                    path,
                    "official_rocm_hip_closure_required",
                )
        elif isinstance(claim_boundary, str) and claim_boundary:
            residual_contract = receipt.get("residual_contract")
            lowered_claim_boundary = claim_boundary.lower()
            state_dependent_hip_contract_valid = (
                isinstance(residual_contract, dict)
                and residual_contract.get(
                    "allow_state_dependent_shell_material_tangent_hip_replay"
                )
                is True
                and residual_contract.get(
                    "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency"
                )
                is True
            )
            fallback_zero_ok = (
                isinstance(gate, dict)
                and gate.get("fallback_zero_passed") is True
            )
            production_residency_boundary_only = (
                "host" in lowered_claim_boundary
                and "production" in lowered_claim_boundary
                and "residency" in lowered_claim_boundary
                and "fallback" not in lowered_claim_boundary
                and "cpu" not in lowered_claim_boundary
                and "unavailable" not in lowered_claim_boundary
                and "blocked" not in lowered_claim_boundary
                and "pending" not in lowered_claim_boundary
                and "required closure" not in lowered_claim_boundary
            )
            if (
                state_dependent_hip_contract_valid
                and fallback_zero_ok
                and production_residency_boundary_only
            ):
                pass
            elif any(
                token in lowered_claim_boundary
                for token in (
                    "cpu",
                    "host",
                    "fallback",
                    "rocm",
                    "hip-required",
                    "hip",
                )
            ):
                _add(
                    "claim_boundary_string_suggests_cpu_or_hip_required",
                    path,
                    claim_boundary,
                )
        receipt_blockers = receipt.get("blockers")
        if isinstance(receipt_blockers, list):
            strict_blockers = [
                blocker
                for blocker in receipt_blockers
                if _blocker_is_strict_boundary(blocker)
            ]
            if strict_blockers:
                _add("strict_child_blockers", path, strict_blockers)
        for collection_name in ("promoted_rows", "rows"):
            rows = receipt.get(collection_name)
            if not isinstance(rows, list):
                continue
            for row_index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                if collection_name == "rows" and not bool(row.get("accepted")):
                    continue
                child_path_value = row.get("child_receipt_path")
                if not child_path_value:
                    continue
                child_path = str(child_path_value)
                if child_path in _seen_paths:
                    continue
                _seen_paths.add(child_path)
                child_receipt = _read_json(Path(child_path))
                if not child_receipt:
                    _add(
                        "child_receipt_unreadable",
                        f"{path}.{collection_name}[{row_index}]",
                        child_path,
                    )
                    continue
                _inspect(child_receipt, child_path)

    _inspect(payload, "$")
    if checked_receipt_count <= 0:
        _add("fallback_zero_evidence_missing", "$", None)
    return {
        "passed": not blockers,
        "checked_receipt_count": int(checked_receipt_count),
        "blockers": blockers,
    }


def _extract_nested_gate_contract(
    child_payload: dict[str, Any],
    child_receipt_path: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    gate = child_payload.get("gate_assessment")
    residual_contract = child_payload.get("residual_contract")
    gate_ok = isinstance(gate, dict)
    contract_ok = isinstance(residual_contract, dict)
    if gate_ok and contract_ok:
        return gate, residual_contract, child_receipt_path
    for collection_name in ("promoted_rows", "rows"):
        candidate_rows = child_payload.get(collection_name)
        if not isinstance(candidate_rows, list):
            continue
        for reverse_index, row in enumerate(reversed(candidate_rows)):
            if not isinstance(row, dict):
                continue
            if not bool(row.get("accepted")):
                continue
            nested_child_path = row.get("child_receipt_path")
            if not nested_child_path:
                continue
            nested_payload = _read_json(Path(str(nested_child_path)))
            nested_gate = nested_payload.get("gate_assessment")
            nested_contract = nested_payload.get("residual_contract")
            if not isinstance(nested_gate, dict) or not isinstance(nested_contract, dict):
                continue
            row_index = len(candidate_rows) - reverse_index - 1
            return nested_gate, nested_contract, (
                f"{child_receipt_path}::{collection_name}[{row_index}]"
                f"->{nested_child_path}"
            )
    gate = gate if gate_ok else {}
    residual_contract = residual_contract if contract_ok else {}
    return gate, residual_contract, child_receipt_path


def _compute_g1_closure_assessment(
    *,
    strict_hip_residual_engine: bool,
    strict_hip_runtime_available: bool,
    promoted_rows: list[dict[str, Any]],
    allow_state_dependent_shell_material_tangent_hip_replay: bool,
    allow_frozen_shell_material_tangent_hip_replay: bool,
) -> dict[str, Any]:
    strict_hip_engine_governs = bool(strict_hip_residual_engine)
    strict_hip_runtime_governs = bool(strict_hip_runtime_available)
    has_promoted = len(promoted_rows) > 0
    evidence_child_receipt_path = (
        str(promoted_rows[-1].get("child_receipt_path")) if has_promoted else ""
    )
    evidence_child_payload = (
        _read_json(Path(evidence_child_receipt_path))
        if evidence_child_receipt_path
        else {}
    )
    gate, residual_contract, evidence_location = _extract_nested_gate_contract(
        evidence_child_payload,
        evidence_child_receipt_path,
    )

    full_load_direct_residual_passed = bool(
        has_promoted and gate.get("direct_residual_gate_passed") is True
    )
    relative_increment_verified = bool(
        has_promoted and gate.get("relative_increment_gate_verified") is True
    )
    relative_increment_passed = bool(
        relative_increment_verified
        and gate.get("relative_increment_gate_passed") is True
    )

    material_newton_state_dependent_passed = bool(
        allow_state_dependent_shell_material_tangent_hip_replay is True
        and residual_contract.get("shell_material_tangent_residual_applied") is True
        and residual_contract.get(
            "allow_state_dependent_shell_material_tangent_hip_replay"
        )
        is True
        and residual_contract.get(
            "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency"
        )
        is True
    )
    hip_residual_engine_contract_passed = bool(
        residual_contract.get("hip_residual_engine_contract_passed") is True
        and residual_contract.get("hip_residual_engine_required") is True
        and int(residual_contract.get("hip_residual_engine_required_lane_count") or 0)
        > 0
        and int(residual_contract.get("hip_residual_engine_passed_lane_count") or 0)
        == int(residual_contract.get("hip_residual_engine_required_lane_count") or 0)
    )

    frozen_only_is_not_state_dependent_closure = (
        allow_frozen_shell_material_tangent_hip_replay is True
        and allow_state_dependent_shell_material_tangent_hip_replay is not True
    )

    fallback_zero_passed = has_promoted and all(
        row.get("strict_fallback_zero_audit", {}).get("passed") is True
        for row in promoted_rows
    )
    child_fallback_zero_passed = bool(
        has_promoted and gate.get("fallback_zero_passed") is True
    )

    g1_closure_claimed = (
        strict_hip_engine_governs
        and strict_hip_runtime_governs
        and full_load_direct_residual_passed
        and relative_increment_passed
        and material_newton_state_dependent_passed
        and hip_residual_engine_contract_passed
        and fallback_zero_passed
        and child_fallback_zero_passed
    )

    blockers: list[str] = []
    if not strict_hip_engine_governs:
        blockers.append("strict_hip_residual_engine_not_enabled")
    if not strict_hip_runtime_governs:
        blockers.append("strict_hip_runtime_unavailable")
    if not has_promoted:
        blockers.append("no_promoted_child_receipt")
    if has_promoted and not full_load_direct_residual_passed:
        blockers.append("child_direct_residual_gate_not_passed")
    if has_promoted and not relative_increment_verified:
        blockers.append("child_relative_increment_gate_not_verified")
    if relative_increment_verified and not relative_increment_passed:
        blockers.append("child_relative_increment_gate_not_passed")
    if has_promoted and not material_newton_state_dependent_passed:
        blockers.append("child_state_dependent_material_newton_gate_not_proven")
    if has_promoted and not hip_residual_engine_contract_passed:
        blockers.append("child_hip_residual_engine_contract_not_proven")
    if has_promoted and not fallback_zero_passed:
        blockers.append("strict_fallback_zero_audit_not_passed")
    if has_promoted and not child_fallback_zero_passed:
        blockers.append("child_fallback_zero_gate_not_passed")

    return {
        "g1_closure_claimed": bool(g1_closure_claimed),
        "strict_hip_engine_governs": strict_hip_engine_governs,
        "strict_hip_runtime_governs": strict_hip_runtime_governs,
        "evidence_child_receipt_path": evidence_child_receipt_path or None,
        "evidence_location": evidence_location or None,
        "full_load_direct_residual_passed": full_load_direct_residual_passed,
        "relative_increment_verified": relative_increment_verified,
        "relative_increment_passed": relative_increment_passed,
        "material_newton_state_dependent_passed": material_newton_state_dependent_passed,
        "hip_residual_engine_contract_passed": hip_residual_engine_contract_passed,
        "frozen_only_is_not_state_dependent_closure": frozen_only_is_not_state_dependent_closure,
        "fallback_zero_passed": fallback_zero_passed,
        "child_fallback_zero_passed": child_fallback_zero_passed,
        "blockers": blockers,
    }


def _rocm_hip_runtime_preflight() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "available": False,
        "torch_imported": False,
        "torch_rocm_build": False,
        "torch_hip_device_available": False,
    }
    try:
        import torch  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - runtime dependent
        payload["reason"] = "torch_import_failed"
        payload["torch_import_error"] = str(exc)
        return payload
    payload["torch_imported"] = True
    payload["torch_version"] = str(getattr(torch, "__version__", ""))
    payload["torch_rocm_version"] = str(getattr(torch.version, "hip", None))
    payload["torch_rocm_build"] = bool(getattr(torch.version, "hip", None))
    if not payload["torch_rocm_build"]:
        payload["reason"] = "torch_build_is_not_rocm"
        return payload
    try:
        hip_available = bool(torch.cuda.is_available())
    except Exception as exc:  # pragma: no cover - runtime dependent
        payload["reason"] = "torch_hip_availability_check_failed"
        payload["torch_hip_availability_error"] = str(exc)
        return payload
    payload["torch_hip_device_available"] = hip_available
    if not hip_available:
        payload["reason"] = "torch_hip_device_unavailable"
        return payload
    try:
        payload["torch_hip_device_name"] = str(torch.cuda.get_device_name(0))
    except Exception as exc:  # pragma: no cover - runtime dependent
        payload["torch_hip_device_name_error"] = str(exc)
    payload["available"] = True
    payload["reason"] = "available"
    return payload


def _run_subprocess_child(
    *,
    command: list[str],
    output_json: Path,
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=float(timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        payload = {
            "schema_version": "mgt-g1-alternating-child-timeout.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "timeout",
            "command": command,
            "child_timeout_seconds": float(timeout_seconds),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "claim_boundary": (
                "Timeout receipt only. No residual progress is claimed because the "
                "child controller did not finish."
            ),
        }
        _write_json(output_json, payload)
        return payload, {
            "subprocess_returncode": None,
            "subprocess_timeout": True,
            "subprocess_stdout": exc.stdout or "",
            "subprocess_stderr": exc.stderr or "",
            "subprocess_command": command,
            "subprocess_timeout_seconds": float(timeout_seconds),
        }
    payload = _read_json(output_json)
    return payload, {
        "subprocess_returncode": int(completed.returncode),
        "subprocess_timeout": False,
        "subprocess_stdout": completed.stdout,
        "subprocess_stderr": completed.stderr,
        "subprocess_command": command,
        "subprocess_timeout_seconds": float(timeout_seconds),
    }


def _row_controller_command(
    *,
    python_exe: Path,
    mgt_path: Path,
    checkpoint_npz: Path,
    seed_probe_json: Path,
    output_json: Path,
    output_checkpoint: Path,
    child_output_dir: Path,
    row_target_counts: tuple[int, ...],
    row_support_column_counts: tuple[int, ...],
    row_alpha_values: tuple[float, ...],
    row_support_selection: str,
    row_fd_max_support_columns: int,
    row_batch_replay_backend: str,
    row_require_hip_batch_replay: bool,
    row_child_timeout_seconds: float,
    runtime_budget_seconds: float,
    allow_frozen_shell_material_tangent_hip_replay: bool = False,
    allow_state_dependent_shell_material_tangent_hip_replay: bool = False,
) -> list[str]:
    script = Path(__file__).resolve().with_name(
        "run_mgt_shell_material_rowcorr_budget_controller.py"
    )
    command = [
        str(python_exe),
        str(script),
        "--mgt-path",
        str(mgt_path),
        "--checkpoint-npz",
        str(checkpoint_npz),
        "--seed-probe-json",
        str(seed_probe_json),
        "--output-json",
        str(output_json),
        "--output-final-checkpoint-npz",
        str(output_checkpoint),
        "--child-output-dir",
        str(child_output_dir),
        "--row-target-mode",
        "current_component_rows",
        "--row-frontier-component-scale-mode",
        "dominant_component_magnitude",
        "--row-jacobian-mode",
        "finite_difference",
        "--row-support-selection",
        str(row_support_selection),
        "--row-fd-epsilon",
        "1e-6",
        "--row-fd-max-support-columns",
        str(int(row_fd_max_support_columns)),
        "--row-batch-fd-replay",
        "--row-batch-fd-replay-chunk-size",
        "32",
        "--row-batch-replay-backend",
        str(row_batch_replay_backend),
        "--row-use-residual-only-assembly",
        "--row-batch-alpha-replay",
        "--row-target-counts",
        _csv(row_target_counts),
        "--row-support-column-counts",
        _csv(row_support_column_counts),
        "--row-alpha-values",
        _csv(row_alpha_values),
        "--max-candidates",
        "1",
        "--max-row-promotions",
        "1",
        "--write-child-checkpoints",
        "--row-min-relative-improvement",
        "1e-6",
        "--controller-min-relative-improvement",
        "1e-6",
        "--shell-pressure-load-path-policy",
        "structural_components_only",
        "--child-timeout-seconds",
        str(float(row_child_timeout_seconds)),
        "--max-controller-runtime-seconds",
        str(float(runtime_budget_seconds)),
    ]
    if not row_require_hip_batch_replay:
        command.insert(2, "--allow-cpu-diagnostic")
    if row_require_hip_batch_replay:
        command.append("--row-require-hip-batch-replay")
    if (
        allow_frozen_shell_material_tangent_hip_replay
        and not allow_state_dependent_shell_material_tangent_hip_replay
    ):
        command.append("--allow-frozen-shell-material-tangent-hip-replay")
    if allow_state_dependent_shell_material_tangent_hip_replay:
        command.append("--allow-state-dependent-shell-material-tangent-hip-replay")
    return command


def _global_controller_command(
    *,
    python_exe: Path,
    mgt_path: Path,
    checkpoint_npz: Path,
    output_json: Path,
    output_checkpoint: Path,
    child_output_dir: Path,
    tangent_regularization_factors: tuple[float, ...],
    preconditioner_input_scales: tuple[float, ...],
    preconditioner_mode: str,
    max_iterations: int,
    difference_scheme: str,
    batch_replay_backend: str,
    require_hip_batch_replay: bool,
    linear_solver_backend: str,
    probe_max_step: float,
    residual_scale_floor: float,
    alpha_values: tuple[float, ...],
    max_alpha: float,
    min_relative_improvement: float,
    enable_secant_family_seed: bool,
    max_secant_family_promotions: int,
    secant_family_window_sizes: tuple[int, ...],
    secant_family_ridge_factors: tuple[float, ...],
    secant_family_alpha_values: tuple[float, ...],
    secant_family_min_relative_improvement: float,
    runtime_budget_seconds: float,
    child_timeout_seconds: float,
    allow_frozen_shell_material_tangent_hip_replay: bool = False,
    allow_state_dependent_shell_material_tangent_hip_replay: bool = False,
) -> list[str]:
    script = Path(__file__).resolve().with_name(
        "run_mgt_direct_residual_adaptive_preconditioned_global_newton.py"
    )
    command = [
        str(python_exe),
        str(script),
        "--mgt-path",
        str(mgt_path),
        "--checkpoint-npz",
        str(checkpoint_npz),
        "--output-json",
        str(output_json),
        "--output-final-checkpoint-npz",
        str(output_checkpoint),
        "--child-output-dir",
        str(child_output_dir),
        "--compact-output-final-checkpoint",
        "--apply-shell-material-tangent",
        "--shell-pressure-load-path-policy",
        "structural_components_only",
        "--adaptive-tangent-regularization-factors",
        _csv(tangent_regularization_factors),
        "--matrix-free-global-krylov-preconditioner-input-scales",
        _csv(preconditioner_input_scales),
        "--matrix-free-global-krylov-preconditioner-mode",
        str(preconditioner_mode),
        "--max-controller-steps",
        "1",
        "--matrix-free-global-krylov-max-iterations",
        str(int(max_iterations)),
        "--matrix-free-global-krylov-difference-scheme",
        str(difference_scheme),
        "--matrix-free-global-krylov-batch-replay-backend",
        str(batch_replay_backend),
        "--matrix-free-global-krylov-linear-solver-backend",
        str(linear_solver_backend),
        "--matrix-free-global-krylov-alpha-values",
        _csv(alpha_values),
        "--matrix-free-global-krylov-max-alpha",
        str(float(max_alpha)),
        "--matrix-free-global-krylov-probe-max-step",
        str(float(probe_max_step)),
        "--matrix-free-global-krylov-residual-scale-floor",
        str(float(residual_scale_floor)),
        "--matrix-free-global-krylov-min-relative-improvement",
        str(float(min_relative_improvement)),
        "--max-controller-runtime-seconds",
        str(float(runtime_budget_seconds)),
        "--child-timeout-seconds",
        str(float(child_timeout_seconds)),
    ]
    if not require_hip_batch_replay:
        command.insert(2, "--allow-cpu-diagnostic")
    if require_hip_batch_replay:
        command.extend(["--matrix-free-global-krylov-require-hip-batch-replay"])
    if enable_secant_family_seed:
        command.extend(
            [
                "--enable-secant-family-seed",
                "--max-secant-family-promotions",
                str(int(max_secant_family_promotions)),
                "--secant-family-window-sizes",
                _csv(secant_family_window_sizes),
                "--secant-family-ridge-factors",
                _csv(secant_family_ridge_factors),
                "--secant-family-alpha-values",
                _csv(secant_family_alpha_values),
                "--secant-family-min-relative-improvement",
                str(float(secant_family_min_relative_improvement)),
            ]
        )
    if (
        allow_frozen_shell_material_tangent_hip_replay
        and not allow_state_dependent_shell_material_tangent_hip_replay
    ):
        command.append("--allow-frozen-shell-material-tangent-hip-replay")
    if allow_state_dependent_shell_material_tangent_hip_replay:
        command.append("--allow-state-dependent-shell-material-tangent-hip-replay")
    return command


def _build_claim_boundary(
    *,
    strict_hip_residual_engine: bool,
    strict_hip_runtime_available: bool,
    stop_reason: str,
    allow_state_dependent_shell_material_tangent_hip_replay: bool,
) -> dict[str, Any]:
    if not strict_hip_residual_engine:
        return {
            "cpu_diagnostic_only": True,
            "official_rocm_hip_closure_required": True,
            "child_receipts_are_source_of_residual_progress": True,
            "timeouts_do_not_claim_descent": True,
            "row_fd_component_lane_is_candidate_generation_only": True,
            "global_krylov_lane_requires_full_assembly_replay": True,
        }

    boundary: dict[str, Any] = {
        "cpu_diagnostic_only": False,
        "official_rocm_hip_closure_required": True,
        "child_receipts_are_source_of_residual_progress": True,
        "timeouts_do_not_claim_descent": True,
        "row_fd_component_lane_is_candidate_generation_only": True,
        "global_krylov_lane_requires_full_assembly_replay": True,
        "strict_hip_residual_engine_active": True,
        "residual_replay_requires_hip_only": True,
        "cpu_fallback_expectation_zero_suppressed": True,
        "rocm_hip_runtime_available": bool(strict_hip_runtime_available),
    }

    if not strict_hip_runtime_available:
        boundary["strict_hip_runtime_preflight_passed"] = False
        boundary["g1_closure_claimed"] = False
    else:
        boundary["strict_hip_runtime_preflight_passed"] = True

    if allow_state_dependent_shell_material_tangent_hip_replay:
        boundary[
            "host_shell_csr_operator_refresh_not_full_production_rocm_hip_residency"
        ] = True

    return boundary


def run_g1_alternating_newton_controller(
    *,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path,
    seed_probe_json: Path,
    output_json: Path = DEFAULT_OUTPUT,
    output_final_checkpoint_npz: Path | None = None,
    child_output_dir: Path | None = None,
    python_exe: Path | None = None,
    max_cycles: int = 1,
    max_controller_runtime_seconds: float | None = None,
    child_timeout_seconds: float = 600.0,
    child_timeout_grace_seconds: float = 30.0,
    min_relative_improvement: float = 1.0e-6,
    lane_sequence: tuple[str, ...] = ("row_fd_component", "global_krylov"),
    row_target_counts: tuple[int, ...] = (12,),
    row_support_column_counts: tuple[int, ...] = (16,),
    row_alpha_values: tuple[float, ...] = (
        0.05,
        0.03,
        0.02,
        0.015,
        0.01,
        0.0075,
        0.005,
        0.0025,
        0.001,
    ),
    row_fd_max_support_columns: int = 16,
    row_support_selection: str = "row_strongest",
    row_batch_replay_backend: str = "cpu",
    row_require_hip_batch_replay: bool = False,
    strict_hip_residual_engine: bool = False,
    global_tangent_regularization_factors: tuple[float, ...] = (1.0e-6,),
    global_preconditioner_input_scales: tuple[float, ...] = (0.25,),
    global_krylov_preconditioner_mode: str = "current_tangent",
    global_krylov_max_iterations: int = 2,
    global_krylov_difference_scheme: str = "forward",
    global_krylov_batch_replay_backend: str = "cpu",
    global_krylov_require_hip_batch_replay: bool = False,
    global_krylov_linear_solver_backend: str = "scipy_host_gmres",
    global_krylov_probe_max_step: float = 1.0e-5,
    global_krylov_residual_scale_floor: float = 1.0,
    global_alpha_values: tuple[float, ...] = (16.0, 8.0, 4.0, 2.0, 1.0, 0.5, 0.25),
    global_max_alpha: float = 16.0,
    global_krylov_min_relative_improvement: float = 1.0e-6,
    global_enable_secant_family_seed: bool = False,
    global_max_secant_family_promotions: int = 1,
    global_secant_family_window_sizes: tuple[int, ...] = (4, 8, 16),
    global_secant_family_ridge_factors: tuple[float, ...] = (0.0, 1.0e-8),
    global_secant_family_alpha_values: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
    ),
    global_secant_family_min_relative_improvement: float = 1.0e-6,
    allow_frozen_shell_material_tangent_hip_replay: bool = False,
    allow_state_dependent_shell_material_tangent_hip_replay: bool = False,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    runtime_budget_seconds = (
        float(max_controller_runtime_seconds)
        if max_controller_runtime_seconds is not None
        else None
    )
    child_output_dir = child_output_dir or output_json.parent / f"{output_json.stem}_children"
    child_output_dir.mkdir(parents=True, exist_ok=True)
    python_exe = python_exe or Path(sys.executable)
    global_krylov_difference_scheme = str(
        global_krylov_difference_scheme
    ).strip().lower()
    if global_krylov_difference_scheme not in {"forward", "central"}:
        global_krylov_difference_scheme = "forward"
    global_krylov_preconditioner_mode = str(
        global_krylov_preconditioner_mode
    ).strip().lower()
    if global_krylov_preconditioner_mode not in {"none", "current_tangent"}:
        global_krylov_preconditioner_mode = "current_tangent"
    if strict_hip_residual_engine:
        row_require_hip_batch_replay = True
        global_krylov_require_hip_batch_replay = True
    row_support_selection = str(row_support_selection).strip().lower()
    if row_support_selection not in {
        "row_strongest",
        "residual_weighted",
        "target_rows",
    }:
        row_support_selection = "row_strongest"
    if row_require_hip_batch_replay and row_batch_replay_backend == "cpu":
        raise ValueError(
            "strict/required HIP residual replay needs a HIP row batch replay backend"
        )
    if (
        global_krylov_require_hip_batch_replay
        and global_krylov_batch_replay_backend == "cpu"
    ):
        raise ValueError(
            "strict/required HIP residual replay needs a HIP global Krylov batch replay backend"
        )
    strict_hip_runtime_preflight: dict[str, Any] | None = None
    strict_hip_runtime_available = True
    if strict_hip_residual_engine:
        strict_hip_runtime_preflight = _rocm_hip_runtime_preflight()
        strict_hip_runtime_available = bool(
            strict_hip_runtime_preflight.get("available")
        )
    global_krylov_preconditioner_mode_disabled_reason = ""
    if (
        global_krylov_require_hip_batch_replay
        and global_krylov_preconditioner_mode == "current_tangent"
    ):
        global_krylov_preconditioner_mode_disabled_reason = (
            "hip_batch_replay_required_suppresses_cpu_current_tangent_preconditioner"
        )
        global_krylov_preconditioner_mode = "none"
    global_krylov_linear_solver_backend = str(
        global_krylov_linear_solver_backend
    ).strip().lower()
    if global_krylov_linear_solver_backend not in {
        "scipy_host_gmres",
        "torch_hip_gmres",
    }:
        global_krylov_linear_solver_backend = "scipy_host_gmres"
    global_krylov_linear_solver_backend_auto_selected_reason = ""
    if (
        global_krylov_require_hip_batch_replay
        and global_krylov_linear_solver_backend == "scipy_host_gmres"
    ):
        global_krylov_linear_solver_backend_auto_selected_reason = (
            "hip_batch_replay_required_suppresses_host_gmres"
        )
        global_krylov_linear_solver_backend = "torch_hip_gmres"

    seed_payload = _read_json(seed_probe_json)
    current_residual = _residual_from_payload(seed_payload)
    current_checkpoint = Path(checkpoint_npz)
    current_seed_json = Path(seed_probe_json)
    rows: list[dict[str, Any]] = []
    promoted_rows: list[dict[str, Any]] = []
    stop_reason = "max_cycles_reached"
    runtime_budget_exceeded = False

    def _remaining_budget() -> float:
        if runtime_budget_seconds is None:
            return float(child_timeout_seconds)
        return max(runtime_budget_seconds - (time.perf_counter() - started), 0.0)

    clean_lane_sequence = tuple(
        lane
        for lane in lane_sequence
        if lane in {"row_fd_component", "global_krylov"}
    ) or ("row_fd_component", "global_krylov")
    max_steps = max(int(max_cycles), 0) * len(clean_lane_sequence)
    if strict_hip_residual_engine and not strict_hip_runtime_available and max_steps > 0:
        stop_reason = "strict_hip_runtime_unavailable"
    for step_index in range(
        1,
        (0 if stop_reason == "strict_hip_runtime_unavailable" else max_steps) + 1,
    ):
        remaining = _remaining_budget()
        if runtime_budget_seconds is not None and remaining <= 0.0:
            runtime_budget_exceeded = True
            stop_reason = "runtime_budget_exceeded"
            break
        child_runtime_budget = min(float(child_timeout_seconds), remaining)
        if child_runtime_budget <= 0.0:
            runtime_budget_exceeded = True
            stop_reason = "runtime_budget_exceeded"
            break
        subprocess_timeout_seconds = child_runtime_budget + max(
            float(child_timeout_grace_seconds),
            0.0,
        )

        lane = clean_lane_sequence[(step_index - 1) % len(clean_lane_sequence)]
        child_json = child_output_dir / f"{output_json.stem}_step{step_index}_{lane}.json"
        child_checkpoint = (
            child_output_dir / f"{output_json.stem}_step{step_index}_{lane}_checkpoint.npz"
        )
        lane_children = child_output_dir / f"{output_json.stem}_step{step_index}_{lane}_children"
        if lane == "row_fd_component":
            command = _row_controller_command(
                python_exe=python_exe,
                mgt_path=mgt_path,
                checkpoint_npz=current_checkpoint,
                seed_probe_json=current_seed_json,
                output_json=child_json,
                output_checkpoint=child_checkpoint,
                child_output_dir=lane_children,
                row_target_counts=row_target_counts,
                row_support_column_counts=row_support_column_counts,
                row_alpha_values=row_alpha_values,
                row_support_selection=row_support_selection,
                row_fd_max_support_columns=row_fd_max_support_columns,
                row_batch_replay_backend=row_batch_replay_backend,
                row_require_hip_batch_replay=row_require_hip_batch_replay,
                row_child_timeout_seconds=child_runtime_budget,
                runtime_budget_seconds=child_runtime_budget,
                allow_frozen_shell_material_tangent_hip_replay=(
                    allow_frozen_shell_material_tangent_hip_replay
                ),
                allow_state_dependent_shell_material_tangent_hip_replay=(
                    allow_state_dependent_shell_material_tangent_hip_replay
                ),
            )
        else:
            command = _global_controller_command(
                python_exe=python_exe,
                mgt_path=mgt_path,
                checkpoint_npz=current_checkpoint,
                output_json=child_json,
                output_checkpoint=child_checkpoint,
                child_output_dir=lane_children,
                tangent_regularization_factors=global_tangent_regularization_factors,
                preconditioner_input_scales=global_preconditioner_input_scales,
                preconditioner_mode=global_krylov_preconditioner_mode,
                max_iterations=global_krylov_max_iterations,
                difference_scheme=global_krylov_difference_scheme,
                batch_replay_backend=global_krylov_batch_replay_backend,
                require_hip_batch_replay=global_krylov_require_hip_batch_replay,
                linear_solver_backend=global_krylov_linear_solver_backend,
                probe_max_step=global_krylov_probe_max_step,
                residual_scale_floor=global_krylov_residual_scale_floor,
                alpha_values=global_alpha_values,
                max_alpha=global_max_alpha,
                min_relative_improvement=global_krylov_min_relative_improvement,
                enable_secant_family_seed=global_enable_secant_family_seed,
                max_secant_family_promotions=global_max_secant_family_promotions,
                secant_family_window_sizes=global_secant_family_window_sizes,
                secant_family_ridge_factors=global_secant_family_ridge_factors,
                secant_family_alpha_values=global_secant_family_alpha_values,
                secant_family_min_relative_improvement=(
                    global_secant_family_min_relative_improvement
                ),
                runtime_budget_seconds=child_runtime_budget,
                child_timeout_seconds=child_runtime_budget,
                allow_frozen_shell_material_tangent_hip_replay=(
                    allow_frozen_shell_material_tangent_hip_replay
                ),
                allow_state_dependent_shell_material_tangent_hip_replay=(
                    allow_state_dependent_shell_material_tangent_hip_replay
                ),
            )
        child_started = time.perf_counter()
        child_payload, subprocess_meta = _run_subprocess_child(
            command=command,
            output_json=child_json,
            timeout_seconds=subprocess_timeout_seconds,
        )
        child_runtime = float(time.perf_counter() - child_started)
        child_final = _residual_from_payload(child_payload)
        improvement = (
            current_residual - child_final
            if current_residual is not None and child_final is not None
            else None
        )
        relative_improvement = (
            improvement / max(current_residual, 1.0e-30)
            if improvement is not None and current_residual is not None
            else None
        )
        strict_fallback_zero_audit = (
            _strict_fallback_zero_audit(child_payload)
            if strict_hip_residual_engine
            else {"passed": True, "checked_receipt_count": 0, "blockers": []}
        )
        accepted = bool(
            _promotion_count(child_payload) > 0
            and child_final is not None
            and improvement is not None
            and relative_improvement is not None
            and improvement > 0.0
            and relative_improvement >= max(float(min_relative_improvement), 0.0)
            and child_checkpoint.is_file()
            and bool(strict_fallback_zero_audit["passed"])
        )
        row = {
            "step_index": int(step_index),
            "lane": lane,
            "child_receipt_path": str(child_json),
            "child_checkpoint_path": str(child_checkpoint),
            "status": child_payload.get("status"),
            "accepted": accepted,
            "child_promotion_count": _promotion_count(child_payload),
            "seed_frontier_direct_residual_inf_n": current_residual,
            "final_direct_residual_inf_n": child_final,
            "frontier_improvement_inf_n": improvement,
            "frontier_relative_improvement": relative_improvement,
            "child_runtime_seconds": child_runtime,
            "child_runtime_budget_seconds": child_runtime_budget,
            "child_timeout_seconds": child_runtime_budget,
            "subprocess_timeout_seconds": subprocess_timeout_seconds,
            "strict_fallback_zero_audit": strict_fallback_zero_audit,
            **subprocess_meta,
        }
        rows.append(row)

        if bool(row.get("subprocess_timeout")):
            runtime_budget_exceeded = True
            stop_reason = "child_timeout_seconds_exceeded"
            break
        if accepted:
            promoted_rows.append(row)
            current_residual = child_final
            current_checkpoint = child_checkpoint
            current_seed_json = child_json
            continue
        if lane == "global_krylov":
            stop_reason = "cycle_without_global_promotion"
            break

    else:
        if max_steps == 0 and stop_reason == "max_cycles_reached":
            stop_reason = "no_steps_requested"

    output_final_checkpoint_written = False
    if (
        output_final_checkpoint_npz is not None
        and promoted_rows
        and current_checkpoint.is_file()
    ):
        output_final_checkpoint_npz.parent.mkdir(parents=True, exist_ok=True)
        if current_checkpoint.resolve() != output_final_checkpoint_npz.resolve():
            shutil.copyfile(current_checkpoint, output_final_checkpoint_npz)
        current_checkpoint = output_final_checkpoint_npz
        output_final_checkpoint_written = True

    g1_closure_assessment = _compute_g1_closure_assessment(
        strict_hip_residual_engine=strict_hip_residual_engine,
        strict_hip_runtime_available=strict_hip_runtime_available,
        promoted_rows=promoted_rows,
        allow_state_dependent_shell_material_tangent_hip_replay=(
            allow_state_dependent_shell_material_tangent_hip_replay
        ),
        allow_frozen_shell_material_tangent_hip_replay=(
            allow_frozen_shell_material_tangent_hip_replay
        ),
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "passed" if g1_closure_assessment["g1_closure_claimed"] else "partial",
        "g1_alternating_newton_controller_ready": True,
        "g1_closure_assessment": g1_closure_assessment,
        "controller": {
            "enabled": True,
            "attempted": True,
            "max_cycles": int(max_cycles),
            "promotion_count": int(len(promoted_rows)),
            "stop_reason": stop_reason,
            "min_relative_improvement": float(min_relative_improvement),
            "runtime_budget_seconds": runtime_budget_seconds,
            "runtime_budget_exceeded": bool(runtime_budget_exceeded),
            "child_timeout_seconds": float(child_timeout_seconds),
            "child_timeout_grace_seconds": float(child_timeout_grace_seconds),
            "lane_sequence": [str(lane) for lane in clean_lane_sequence],
            "row_target_counts": [int(value) for value in row_target_counts],
            "row_support_column_counts": [
                int(value) for value in row_support_column_counts
            ],
            "row_fd_max_support_columns": int(row_fd_max_support_columns),
            "row_support_selection": str(row_support_selection),
            "row_batch_replay_backend": str(row_batch_replay_backend),
            "row_require_hip_batch_replay": bool(row_require_hip_batch_replay),
            "strict_hip_residual_engine": bool(strict_hip_residual_engine),
            "strict_hip_residual_engine_fallback_zero_expectation": bool(
                strict_hip_residual_engine
            ),
            "strict_hip_runtime_preflight": strict_hip_runtime_preflight,
            "global_tangent_regularization_factors": [
                float(value) for value in global_tangent_regularization_factors
            ],
            "global_preconditioner_input_scales": [
                float(value) for value in global_preconditioner_input_scales
            ],
            "global_krylov_preconditioner_mode": str(
                global_krylov_preconditioner_mode
            ),
            "global_krylov_preconditioner_mode_disabled_reason": (
                global_krylov_preconditioner_mode_disabled_reason
            ),
            "global_krylov_max_iterations": int(global_krylov_max_iterations),
            "global_krylov_difference_scheme": global_krylov_difference_scheme,
            "global_krylov_batch_replay_backend": str(
                global_krylov_batch_replay_backend
            ),
            "global_krylov_require_hip_batch_replay": bool(
                global_krylov_require_hip_batch_replay
            ),
            "allow_frozen_shell_material_tangent_hip_replay": bool(
                allow_frozen_shell_material_tangent_hip_replay
            ),
            "allow_state_dependent_shell_material_tangent_hip_replay": bool(
                allow_state_dependent_shell_material_tangent_hip_replay
            ),
            "global_krylov_linear_solver_backend": str(
                global_krylov_linear_solver_backend
            ),
            "global_krylov_linear_solver_backend_auto_selected_reason": (
                global_krylov_linear_solver_backend_auto_selected_reason
            ),
            "global_krylov_probe_max_step": float(global_krylov_probe_max_step),
            "global_krylov_residual_scale_floor": float(
                global_krylov_residual_scale_floor
            ),
            "global_krylov_min_relative_improvement": float(
                global_krylov_min_relative_improvement
            ),
            "global_secant_family_seed_enabled": bool(
                global_enable_secant_family_seed
            ),
            "global_max_secant_family_promotions": int(
                global_max_secant_family_promotions
            ),
            "global_secant_family_window_sizes": [
                int(value) for value in global_secant_family_window_sizes
            ],
            "global_secant_family_ridge_factors": [
                float(value) for value in global_secant_family_ridge_factors
            ],
            "global_secant_family_alpha_values": [
                float(value) for value in global_secant_family_alpha_values
            ],
            "global_secant_family_min_relative_improvement": float(
                global_secant_family_min_relative_improvement
            ),
        },
        "initial_checkpoint_path": str(checkpoint_npz),
        "final_checkpoint_path": str(current_checkpoint),
        "output_final_checkpoint_written": bool(output_final_checkpoint_written),
        "initial_frontier_direct_residual_inf_n": _residual_from_payload(seed_payload),
        "final_direct_residual_inf_n": current_residual,
        "rows": rows,
        "promoted_rows": promoted_rows,
        "runtime_seconds": float(time.perf_counter() - started),
        "claim_boundary": _build_claim_boundary(
            strict_hip_residual_engine=strict_hip_residual_engine,
            strict_hip_runtime_available=strict_hip_runtime_available,
            stop_reason=stop_reason,
            allow_state_dependent_shell_material_tangent_hip_replay=(
                allow_state_dependent_shell_material_tangent_hip_replay
            ),
        ),
    }
    _write_json(output_json, payload)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint-npz", type=Path, required=True)
    parser.add_argument("--seed-probe-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-final-checkpoint-npz", type=Path, default=None)
    parser.add_argument("--child-output-dir", type=Path, default=None)
    parser.add_argument("--python-exe", type=Path, default=Path(sys.executable))
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--max-controller-runtime-seconds", type=float, default=None)
    parser.add_argument("--child-timeout-seconds", type=float, default=600.0)
    parser.add_argument("--child-timeout-grace-seconds", type=float, default=30.0)
    parser.add_argument("--min-relative-improvement", type=float, default=1.0e-6)
    parser.add_argument(
        "--lane-sequence",
        default="row_fd_component,global_krylov",
        help=(
            "Comma-separated lane order repeated for max cycles. Supported aliases: "
            "row,row_fd,row_fd_component,global,krylov,global_krylov."
        ),
    )
    parser.add_argument("--row-target-counts", default="12")
    parser.add_argument("--row-support-column-counts", default="16")
    parser.add_argument(
        "--row-alpha-values",
        default="0.05,0.03,0.02,0.015,0.01,0.0075,0.005,0.0025,0.001",
    )
    parser.add_argument("--row-fd-max-support-columns", type=int, default=16)
    parser.add_argument(
        "--row-support-selection",
        choices=("row_strongest", "residual_weighted", "target_rows"),
        default="row_strongest",
    )
    parser.add_argument(
        "--row-batch-replay-backend",
        choices=("cpu", "hip_full_residual", "hip_full_residual_resident", "rust_hip_full_residual_ffi"),
        default="cpu",
    )
    parser.add_argument("--row-require-hip-batch-replay", action="store_true")
    parser.add_argument("--strict-hip-residual-engine", action="store_true")
    parser.add_argument("--global-tangent-regularization-factors", default="1e-6")
    parser.add_argument("--global-preconditioner-input-scales", default="0.25")
    parser.add_argument(
        "--global-krylov-preconditioner-mode",
        choices=("none", "current_tangent"),
        default="current_tangent",
    )
    parser.add_argument("--global-krylov-max-iterations", type=int, default=2)
    parser.add_argument(
        "--global-krylov-difference-scheme",
        choices=("forward", "central"),
        default="forward",
    )
    parser.add_argument(
        "--global-krylov-batch-replay-backend",
        choices=("cpu", "hip_full_residual", "hip_full_residual_resident", "rust_hip_full_residual_ffi"),
        default="cpu",
    )
    parser.add_argument("--global-krylov-require-hip-batch-replay", action="store_true")
    parser.add_argument(
        "--allow-frozen-shell-material-tangent-hip-replay",
        action="store_true",
        help=(
            "Forward frozen shell-material tangent HIP replay to child "
            "controllers. Frozen replay is NOT material Newton closure and "
            "does NOT satisfy strict G1 closure by itself."
        ),
    )
    parser.add_argument(
        "--allow-state-dependent-shell-material-tangent-hip-replay",
        action="store_true",
        help=(
            "Forward candidate-state shell-material tangent HIP replay to child "
            "controllers. Residual replay stays on HIP, but host shell operator "
            "refresh is not production residency closure."
        ),
    )
    parser.add_argument(
        "--global-krylov-linear-solver-backend",
        choices=("scipy_host_gmres", "torch_hip_gmres"),
        default="scipy_host_gmres",
    )
    parser.add_argument("--global-krylov-probe-max-step", type=float, default=1.0e-5)
    parser.add_argument(
        "--global-krylov-residual-scale-floor",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--global-alpha-values",
        default="16,8,4,2,1,0.5,0.25",
    )
    parser.add_argument("--global-max-alpha", type=float, default=16.0)
    parser.add_argument(
        "--global-krylov-min-relative-improvement",
        type=float,
        default=1.0e-6,
    )
    parser.add_argument("--global-enable-secant-family-seed", action="store_true")
    parser.add_argument("--global-max-secant-family-promotions", type=int, default=1)
    parser.add_argument("--global-secant-family-window-sizes", default="4,8,16")
    parser.add_argument("--global-secant-family-ridge-factors", default="0,1e-8")
    parser.add_argument(
        "--global-secant-family-alpha-values",
        default="1,0.5,0.25,0.125,0.0625",
    )
    parser.add_argument(
        "--global-secant-family-min-relative-improvement",
        type=float,
        default=1.0e-6,
    )
    parser.add_argument("--allow-cpu-diagnostic", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.strict_hip_residual_engine:
        args.row_require_hip_batch_replay = True
        args.global_krylov_require_hip_batch_replay = True
    if (
        args.row_require_hip_batch_replay
        and args.row_batch_replay_backend == "cpu"
    ):
        print(
            "mgt-g1-alternating-newton-controller: blocked "
            "--row-require-hip-batch-replay requires a HIP batch replay backend",
            file=sys.stderr,
        )
        return 2
    if (
        args.global_krylov_require_hip_batch_replay
        and args.global_krylov_batch_replay_backend == "cpu"
    ):
        print(
            "mgt-g1-alternating-newton-controller: blocked "
            "--global-krylov-require-hip-batch-replay requires a HIP batch replay backend",
            file=sys.stderr,
        )
        return 2
    if not args.strict_hip_residual_engine and not args.allow_cpu_diagnostic:
        print(
            "mgt-g1-alternating-newton-controller: blocked cpu diagnostic requires "
            "--allow-cpu-diagnostic",
            file=sys.stderr,
        )
        return 2
    payload = run_g1_alternating_newton_controller(
        mgt_path=args.mgt_path,
        checkpoint_npz=args.checkpoint_npz,
        seed_probe_json=args.seed_probe_json,
        output_json=args.output_json,
        output_final_checkpoint_npz=args.output_final_checkpoint_npz,
        child_output_dir=args.child_output_dir,
        python_exe=args.python_exe,
        max_cycles=args.max_cycles,
        max_controller_runtime_seconds=args.max_controller_runtime_seconds,
        child_timeout_seconds=args.child_timeout_seconds,
        child_timeout_grace_seconds=args.child_timeout_grace_seconds,
        min_relative_improvement=args.min_relative_improvement,
        lane_sequence=_parse_lane_sequence(args.lane_sequence),
        row_target_counts=_parse_int_csv(args.row_target_counts) or (12,),
        row_support_column_counts=_parse_int_csv(args.row_support_column_counts) or (16,),
        row_alpha_values=_parse_float_csv(args.row_alpha_values),
        row_fd_max_support_columns=args.row_fd_max_support_columns,
        row_support_selection=args.row_support_selection,
        row_batch_replay_backend=args.row_batch_replay_backend,
        row_require_hip_batch_replay=args.row_require_hip_batch_replay,
        strict_hip_residual_engine=args.strict_hip_residual_engine,
        global_tangent_regularization_factors=_parse_float_csv(
            args.global_tangent_regularization_factors
        )
        or (1.0e-6,),
        global_preconditioner_input_scales=_parse_float_csv(
            args.global_preconditioner_input_scales
        )
        or (0.25,),
        global_krylov_preconditioner_mode=args.global_krylov_preconditioner_mode,
        global_krylov_max_iterations=args.global_krylov_max_iterations,
        global_krylov_difference_scheme=args.global_krylov_difference_scheme,
        global_krylov_batch_replay_backend=args.global_krylov_batch_replay_backend,
        global_krylov_require_hip_batch_replay=(
            args.global_krylov_require_hip_batch_replay
        ),
        global_krylov_linear_solver_backend=args.global_krylov_linear_solver_backend,
        global_krylov_probe_max_step=args.global_krylov_probe_max_step,
        global_krylov_residual_scale_floor=args.global_krylov_residual_scale_floor,
        global_alpha_values=_parse_float_csv(args.global_alpha_values)
        or (16.0, 8.0, 4.0, 2.0, 1.0, 0.5, 0.25),
        global_max_alpha=args.global_max_alpha,
        global_krylov_min_relative_improvement=args.global_krylov_min_relative_improvement,
        global_enable_secant_family_seed=args.global_enable_secant_family_seed,
        global_max_secant_family_promotions=args.global_max_secant_family_promotions,
        global_secant_family_window_sizes=_parse_int_csv(
            args.global_secant_family_window_sizes
        )
        or (4, 8, 16),
        global_secant_family_ridge_factors=_parse_float_csv(
            args.global_secant_family_ridge_factors
        )
        or (0.0, 1.0e-8),
        global_secant_family_alpha_values=_parse_float_csv(
            args.global_secant_family_alpha_values
        )
        or (1.0, 0.5, 0.25, 0.125, 0.0625),
        global_secant_family_min_relative_improvement=(
            args.global_secant_family_min_relative_improvement
        ),
        allow_frozen_shell_material_tangent_hip_replay=(
            args.allow_frozen_shell_material_tangent_hip_replay
        ),
        allow_state_dependent_shell_material_tangent_hip_replay=(
            args.allow_state_dependent_shell_material_tangent_hip_replay
        ),
    )
    controller = payload["controller"]
    print(
        "mgt-g1-alternating-newton-controller: "
        f"status={payload['status']} promotions={controller['promotion_count']} "
        f"stop={controller['stop_reason']} final={payload['final_direct_residual_inf_n']} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
