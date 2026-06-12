#!/usr/bin/env python3
"""Run delivery evidence gates (reanalysis, proxy, commercial crossval) and bundle JSON."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STEP_TIMEOUT_SECONDS = 300
CURRENT_STEP_TIMEOUT_SECONDS = DEFAULT_STEP_TIMEOUT_SECONDS
CURRENT_RERUN_HEAVY_PROBES = False
HEAVY_RECEIPT_SCRIPT_NAMES = {
    "run_mgt_pdelta_continuation_probe.py",
    "run_mgt_coarsened_authored_support_pdelta_probe.py",
    "run_mgt_uncoarsened_boundary_pdelta_probe.py",
    "run_mgt_rocm_sparse_solver_probe.py",
    "run_mgt_coupled_frame_surface_sparse_equilibrium.py",
    "run_mgt_coupled_frame_shell_sparse_equilibrium.py",
    "run_mgt_coupled_frame_shell_story_eccentricity_equilibrium.py",
}


def _output_path_from_command(cmd: list[str]) -> Path | None:
    for flag in ("--output-json", "--out"):
        if flag in cmd:
            index = cmd.index(flag)
            if index + 1 < len(cmd):
                return Path(cmd[index + 1])
    return None


def _heavy_receipt_script_name(cmd: list[str]) -> str:
    if len(cmd) < 2:
        return ""
    return Path(cmd[1]).name


def _run(
    cmd: list[str],
    *,
    timeout_seconds: int | None = None,
    force_rerun: bool = False,
) -> tuple[int, str]:
    timeout = CURRENT_STEP_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    script_name = _heavy_receipt_script_name(cmd)
    output_path = _output_path_from_command(cmd)
    if (
        not force_rerun
        and not CURRENT_RERUN_HEAVY_PROBES
        and script_name in HEAVY_RECEIPT_SCRIPT_NAMES
        and output_path is not None
        and output_path.is_file()
    ):
        return (
            0,
            (
                f"reused_existing_heavy_receipt={output_path} "
                f"script={script_name} timeout_seconds={timeout}"
            ),
        )
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return (
            124,
            (
                f"delivery_step_timeout_after={timeout}s "
                f"cmd={' '.join(str(part) for part in cmd)}\n{output}"
            ).strip(),
        )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def build_productization_status_command(
    script_name: str,
    *,
    productization_dir: Path,
    output_json: Path,
) -> list[str]:
    """Build a status/governance command with explicit evidence input and output paths."""
    return [
        sys.executable,
        str(REPO_ROOT / "scripts" / script_name),
        "--productization-dir",
        str(productization_dir),
        "--output-json",
        str(output_json),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/delivery_evidence_bundle.json",
    )
    parser.add_argument(
        "--changes-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json",
    )
    parser.add_argument(
        "--roundtrip-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
    )
    parser.add_argument(
        "--cases-json",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/commercial_benchmark_cases.from_csv.json",
    )
    parser.add_argument(
        "--residual-holdout-json",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json",
        help="Source RH sidecar to seed the bundle output directory.",
    )
    parser.add_argument("--enrich-changes", action="store_true", help="Run member_alignment enrich first.")
    parser.add_argument(
        "--parse-roundtrip",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Re-parse optimized MGT into roundtrip JSON+NPZ (default on; use --no-parse-roundtrip for sha-only).",
    )
    parser.add_argument(
        "--step-timeout-seconds",
        type=int,
        default=DEFAULT_STEP_TIMEOUT_SECONDS,
        help="Per-child process timeout. Timed-out steps are recorded with exit code 124.",
    )
    parser.add_argument(
        "--rerun-heavy-rocm-probe",
        action="store_true",
        help=(
            "Re-run the heavy ROCm sparse solver probe instead of reusing an existing receipt. "
            "The default keeps delivery bundling bounded and leaves official ROCm closure evidence "
            "to the dedicated probe command."
        ),
    )
    parser.add_argument(
        "--rerun-heavy-probes",
        action="store_true",
        help=(
            "Re-run heavy nonlinear/GPU probe receipts during bundling. By default, delivery bundling "
            "reuses existing heavy receipts and records that reuse so the orchestrator remains bounded."
        ),
    )
    args = parser.parse_args()
    out_dir = args.output_json.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    global CURRENT_STEP_TIMEOUT_SECONDS
    global CURRENT_RERUN_HEAVY_PROBES
    step_timeout_seconds = max(1, int(args.step_timeout_seconds))
    CURRENT_STEP_TIMEOUT_SECONDS = step_timeout_seconds
    CURRENT_RERUN_HEAVY_PROBES = bool(args.rerun_heavy_probes)
    rh_path = out_dir / "residual_holdout_closure_updates.json"
    rh_packet_dir = out_dir / "rh_signed_closure_packets"
    same_rh_path = args.residual_holdout_json.resolve() == rh_path.resolve()
    if not same_rh_path and not rh_path.is_file() and args.residual_holdout_json.is_file():
        shutil.copyfile(args.residual_holdout_json, rh_path)

    steps: list[dict[str, object]] = []
    mgt_path = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
    sync_out = out_dir / "mgt_roundtrip_sync.json"
    sync_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/sync_optimized_mgt_roundtrip.py"),
        "--mgt",
        str(mgt_path),
        "--roundtrip-json",
        str(args.roundtrip_json),
        "--output-json",
        str(sync_out),
    ]
    if args.parse_roundtrip:
        sync_cmd.append("--parse")
    else:
        sync_cmd.append("--sync-only")
    code, log = _run(sync_cmd)
    steps.append({"step": "mgt_roundtrip_sync", "exit_code": code, "log": log})

    global_fea_out = out_dir / "mgt_global_fea_readiness_gate.json"
    mgt_fingerprint_out = out_dir / "mgt_roundtrip_assembly_fingerprint.json"
    mgt_mesh_contract_out = out_dir / "mgt_global_fea_mesh_contract_gate.json"
    rh_html_out = out_dir / "rh_engineer_review_packet_template.html"
    rh_checklist_out = out_dir / "rh_closure_checklist.json"
    rh_template_out = out_dir / "rh_signed_closure_packet_template.json"
    ml_status_out = out_dir / "ml_multi_objective_status.json"
    ai_engine_contracts_out = out_dir / "ai_engine_productization_contracts.json"
    productization_validate_out = out_dir / "productization_delivery_evidence_validation.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_readiness_gate.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(global_fea_out),
        ]
    )
    steps.append({"step": "mgt_global_fea_readiness", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_roundtrip_assembly_fingerprint.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_fingerprint_out),
        ]
    )
    steps.append({"step": "mgt_roundtrip_assembly_fingerprint", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_mesh_contract_gate.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_mesh_contract_out),
        ]
    )
    steps.append({"step": "mgt_global_fea_mesh_contract", "exit_code": code, "log": log})
    mesh_contract_exit = code

    loadcomb_gate_out = out_dir / "load_combination_engine_gate.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "implementation/phase1/run_load_combination_engine_gate.py"),
            "--model-jsons",
            str(args.roundtrip_json),
            "--out",
            str(loadcomb_gate_out),
        ]
    )
    steps.append({"step": "load_combination_engine_gate", "exit_code": code, "log": log})

    load_stage_contract_out = out_dir / "load_stage_semantics_contract.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_load_stage_semantics_contract.py"),
            "--productization-dir",
            str(out_dir),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(load_stage_contract_out),
        ]
    )
    steps.append({"step": "load_stage_semantics_contract", "exit_code": code, "log": log})

    pareto_archive_out = out_dir / "optimization_pareto_research_archive.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_optimization_pareto_research_archive.py"),
            "--changes-json",
            str(args.changes_json),
            "--output-json",
            str(pareto_archive_out),
        ]
    )
    steps.append({"step": "optimization_pareto_research_archive", "exit_code": code, "log": log})

    ml_checkpoint_manifest_out = out_dir / "ml_surrogate_checkpoint_manifest.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ml_surrogate_checkpoint.py"),
            "--productization-dir",
            str(out_dir),
            "--output-json",
            str(ml_checkpoint_manifest_out),
        ]
    )
    steps.append({"step": "ml_surrogate_checkpoint", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_ml_multi_objective_status.py"),
            "--output-json",
            str(ml_status_out),
        ]
    )
    steps.append({"step": "ml_multi_objective_status", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_engine_productization_contracts.py"),
            "--productization-dir",
            str(out_dir),
            "--output-json",
            str(ai_engine_contracts_out),
        ]
    )
    steps.append({"step": "ai_engine_productization_contracts", "exit_code": code, "log": log})

    if args.enrich_changes:
        code, log = _run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/enrich_optimization_changes_contract.py"),
                "--changes-json",
                str(args.changes_json),
            ]
        )
        steps.append({"step": "enrich_member_alignment", "exit_code": code, "log": log})

    crossval_out = out_dir / "commercial_solver_cross_validation.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/report_commercial_solver_cross_validation.py"),
            "--cases-json",
            str(args.cases_json),
            "--output-json",
            str(crossval_out),
        ]
    )
    steps.append({"step": "commercial_cross_validation", "exit_code": code, "log": log})

    native_modal_buckling_out = out_dir / "mgt_native_modal_buckling_solver.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_native_modal_buckling_solver.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--commercial-crossval-json",
            str(crossval_out),
            "--output-json",
            str(native_modal_buckling_out),
        ]
    )
    steps.append({"step": "mgt_native_modal_buckling_solver", "exit_code": code, "log": log})

    proxy_out = out_dir / "proxy_solver_divergence_gate.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_proxy_solver_divergence_gate.py"),
            "--changes-json",
            str(args.changes_json),
            "--output-json",
            str(proxy_out),
        ]
    )
    steps.append({"step": "proxy_solver_divergence", "exit_code": code, "log": log})

    mgt_pipeline_out = out_dir / "mgt_native_reanalysis_pipeline.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_native_reanalysis_pipeline.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--changes-json",
            str(args.changes_json),
            "--output-json",
            str(mgt_pipeline_out),
            "--sync-provenance",
        ]
        + (["--refresh-parse"] if args.parse_roundtrip else [])
    )
    steps.append({"step": "mgt_native_reanalysis_pipeline", "exit_code": code, "log": log})

    mgt_3d_out = out_dir / "mgt_global_fea_3d_native_solve.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_3d_native_solve.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_3d_out),
            "--commercial-crossval-json",
            str(out_dir / "commercial_solver_cross_validation.json"),
        ]
    )
    steps.append({"step": "mgt_global_fea_3d_native_solve", "exit_code": code, "log": log})

    mgt_full_line_sparse_out = out_dir / "mgt_full_line_mesh_sparse_equilibrium.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_full_line_mesh_sparse_equilibrium.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_full_line_sparse_out),
        ]
    )
    steps.append({"step": "mgt_full_line_mesh_sparse_equilibrium", "exit_code": code, "log": log})

    mgt_full_frame_6dof_out = out_dir / "mgt_full_frame_6dof_sparse_equilibrium.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_full_frame_6dof_sparse_equilibrium.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_full_frame_6dof_out),
        ]
    )
    steps.append({"step": "mgt_full_frame_6dof_sparse_equilibrium", "exit_code": code, "log": log})

    mgt_pdelta_continuation_out = out_dir / "mgt_pdelta_continuation_probe.json"
    if args.rerun_heavy_probes or not mgt_pdelta_continuation_out.is_file():
        code, log = _run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/run_mgt_pdelta_continuation_probe.py"),
                "--roundtrip-json",
                str(args.roundtrip_json),
                "--output-json",
                str(mgt_pdelta_continuation_out),
                "--frontier-correction-passes",
                "4",
            ]
        )
        steps.append(
            {
                "step": "mgt_pdelta_continuation_probe",
                "exit_code": code,
                "log": log,
                "execution_mode": "rerun",
                "timeout_seconds": int(step_timeout_seconds),
            }
        )
    else:
        steps.append(
            {
                "step": "mgt_pdelta_continuation_probe",
                "exit_code": 0,
                "log": f"reused_existing_receipt={mgt_pdelta_continuation_out}",
                "execution_mode": "reuse_existing_receipt",
                "timeout_seconds": int(step_timeout_seconds),
            }
        )

    mgt_coarsened_authored_support_pdelta_out = (
        out_dir / "mgt_coarsened_authored_support_pdelta_probe.json"
    )
    if args.rerun_heavy_probes or not mgt_coarsened_authored_support_pdelta_out.is_file():
        code, log = _run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/run_mgt_coarsened_authored_support_pdelta_probe.py"),
                "--roundtrip-json",
                str(args.roundtrip_json),
                "--output-json",
                str(mgt_coarsened_authored_support_pdelta_out),
            ]
        )
        steps.append(
            {
                "step": "mgt_coarsened_authored_support_pdelta_probe",
                "exit_code": code,
                "log": log,
                "execution_mode": "rerun",
                "timeout_seconds": int(step_timeout_seconds),
            }
        )
    else:
        steps.append(
            {
                "step": "mgt_coarsened_authored_support_pdelta_probe",
                "exit_code": 0,
                "log": f"reused_existing_receipt={mgt_coarsened_authored_support_pdelta_out}",
                "execution_mode": "reuse_existing_receipt",
                "timeout_seconds": int(step_timeout_seconds),
            }
        )

    mgt_uncoarsened_boundary_pdelta_out = out_dir / "mgt_uncoarsened_boundary_pdelta_probe.json"
    if args.rerun_heavy_probes or not mgt_uncoarsened_boundary_pdelta_out.is_file():
        code, log = _run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/run_mgt_uncoarsened_boundary_pdelta_probe.py"),
                "--output-json",
                str(mgt_uncoarsened_boundary_pdelta_out),
                "--load-steps",
                "0.05,0.1,0.2,0.25,0.3,0.35,0.36,0.37,0.38,0.39,0.4,0.41,0.42,0.43,0.44,0.45,0.455",
                "--max-iterations-per-step",
                "5",
                "--relaxation-factor",
                "1.0",
            ]
        )
        steps.append(
            {
                "step": "mgt_uncoarsened_boundary_pdelta_probe",
                "exit_code": code,
                "log": log,
                "execution_mode": "rerun",
                "timeout_seconds": int(step_timeout_seconds),
            }
        )
    else:
        steps.append(
            {
                "step": "mgt_uncoarsened_boundary_pdelta_probe",
                "exit_code": 0,
                "log": f"reused_existing_receipt={mgt_uncoarsened_boundary_pdelta_out}",
                "execution_mode": "reuse_existing_receipt",
                "timeout_seconds": int(step_timeout_seconds),
            }
        )

    mgt_surface_membrane_out = out_dir / "mgt_surface_membrane_tangent.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_surface_membrane_tangent.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_surface_membrane_out),
        ]
    )
    steps.append({"step": "mgt_surface_membrane_tangent", "exit_code": code, "log": log})

    mgt_surface_shell_bending_out = out_dir / "mgt_surface_shell_bending_tangent.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_surface_shell_bending_tangent.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_surface_shell_bending_out),
        ]
    )
    steps.append({"step": "mgt_surface_shell_bending_tangent", "exit_code": code, "log": log})

    mgt_shell_calibration_out = out_dir / "mgt_shell_calibration_benchmarks.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_shell_calibration_benchmarks.py"),
            "--output-json",
            str(mgt_shell_calibration_out),
        ]
    )
    steps.append({"step": "mgt_shell_calibration_benchmarks", "exit_code": code, "log": log})

    mgt_coupled_frame_surface_out = out_dir / "mgt_coupled_frame_surface_sparse_equilibrium.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_coupled_frame_surface_sparse_equilibrium.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_coupled_frame_surface_out),
        ]
    )
    steps.append({"step": "mgt_coupled_frame_surface_sparse_equilibrium", "exit_code": code, "log": log})

    mgt_coupled_frame_shell_out = out_dir / "mgt_coupled_frame_shell_sparse_equilibrium.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_coupled_frame_shell_sparse_equilibrium.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_coupled_frame_shell_out),
        ]
    )
    steps.append({"step": "mgt_coupled_frame_shell_sparse_equilibrium", "exit_code": code, "log": log})

    mgt_condensed_out = out_dir / "mgt_global_fea_condensed_solve.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_global_fea_condensed_solve.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_condensed_out),
        ]
    )
    steps.append({"step": "mgt_global_fea_condensed_solve", "exit_code": code, "log": log})

    mgt_frame_material_nonlinear_out = out_dir / "mgt_frame_material_nonlinear_tangent.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_frame_material_nonlinear_tangent.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_frame_material_nonlinear_out),
        ]
    )
    steps.append({"step": "mgt_frame_material_nonlinear_tangent", "exit_code": code, "log": log})

    material_element_tangent_out = out_dir / "material_element_tangent_support_matrix.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_material_element_tangent_support_matrix.py"),
            "--productization-dir",
            str(out_dir),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(material_element_tangent_out),
        ]
    )
    steps.append({"step": "material_element_tangent_support_matrix", "exit_code": code, "log": log})

    mgt_beam_offset_support_out = out_dir / "mgt_beam_offset_support_receipt.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_beam_offset_support_receipt.py"),
            "--output-json",
            str(mgt_beam_offset_support_out),
        ]
    )
    steps.append({"step": "mgt_beam_offset_support_receipt", "exit_code": code, "log": log})

    mgt_local_axis_opening_out = out_dir / "mgt_element_local_axis_opening_semantics_receipt.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_element_local_axis_opening_semantics_receipt.py"),
            "--frame-solve-json",
            str(mgt_full_frame_6dof_out),
            "--output-json",
            str(mgt_local_axis_opening_out),
        ]
    )
    steps.append({"step": "mgt_element_local_axis_opening_semantics_receipt", "exit_code": code, "log": log})

    mgt_boundary_entity_support_out = out_dir / "mgt_boundary_entity_support_receipt.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_boundary_entity_support_receipt.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_boundary_entity_support_out),
        ]
    )
    steps.append({"step": "mgt_boundary_entity_support_receipt", "exit_code": code, "log": log})

    mgt_boundary_spring_tangent_out = out_dir / "mgt_boundary_spring_tangent_receipt.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_boundary_spring_tangent_receipt.py"),
            "--output-json",
            str(mgt_boundary_spring_tangent_out),
        ]
    )
    steps.append({"step": "mgt_boundary_spring_tangent_receipt", "exit_code": code, "log": log})

    mgt_uncoarsened_boundary_global_out = out_dir / "mgt_uncoarsened_boundary_global_equilibrium.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_uncoarsened_boundary_global_equilibrium.py"),
            "--output-json",
            str(mgt_uncoarsened_boundary_global_out),
        ]
    )
    steps.append({"step": "mgt_uncoarsened_boundary_global_equilibrium", "exit_code": code, "log": log})

    mgt_story_eccentricity_load_out = out_dir / "mgt_story_eccentricity_load_receipt.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_mgt_story_eccentricity_load_receipt.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_story_eccentricity_load_out),
        ]
    )
    steps.append({"step": "mgt_story_eccentricity_load_receipt", "exit_code": code, "log": log})

    mgt_coupled_frame_shell_story_eccentricity_out = (
        out_dir / "mgt_coupled_frame_shell_story_eccentricity_equilibrium.json"
    )
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_coupled_frame_shell_story_eccentricity_equilibrium.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(mgt_coupled_frame_shell_story_eccentricity_out),
        ]
    )
    steps.append({"step": "mgt_coupled_frame_shell_story_eccentricity_equilibrium", "exit_code": code, "log": log})

    load_stage_runtime_flow_out = out_dir / "load_stage_runtime_flow_receipt.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_load_stage_runtime_flow_receipt.py"),
            "--productization-dir",
            str(out_dir),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(load_stage_runtime_flow_out),
        ]
    )
    steps.append({"step": "load_stage_runtime_flow_receipt", "exit_code": code, "log": log})

    midas_result_out = (
        REPO_ROOT
        / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.json"
    )
    skip_model_derived = str(os.environ.get("PHASE1_SKIP_MODEL_DERIVED_MIDAS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    # This model defines DEAD/LIVE/WIND load cases only (no seismic), so the wind track is the
    # design-consistent default. Override with PHASE1_MIDAS_SAME_MESH_TRACK=seismic if desired.
    track = str(os.environ.get("PHASE1_MIDAS_SAME_MESH_TRACK") or "wind").strip().lower()
    mgt_path = args.roundtrip_json.with_suffix(".mgt").parent / "midas_generator_33.optimized.mgt"
    if not skip_model_derived:
        if track == "seismic":
            extract_cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts/extract_midas_gen_same_mesh_result.py"),
                "--mgt-path",
                str(mgt_path),
                "--roundtrip-json",
                str(args.roundtrip_json),
                "--condensed-solve-json",
                str(mgt_condensed_out),
                "--output-json",
                str(midas_result_out),
            ]
            extract_step = "midas_model_derived_extract_seismic"
        else:
            extract_cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts/extract_midas_wind_same_mesh_result.py"),
                "--mgt-path",
                str(mgt_path),
                "--roundtrip-json",
                str(args.roundtrip_json),
                "--output-json",
                str(midas_result_out),
            ]
            extract_step = "midas_model_derived_extract_wind"
        code, log = _run(extract_cmd)
        steps.append({"step": extract_step, "exit_code": code, "log": log, "track": track})

    resolve_code, resolve_log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/resolve_midas_same_mesh_result_path.py"),
            "--roundtrip-json",
            str(args.roundtrip_json),
        ]
    )
    midas_resolution_kind = "default_proxy"
    if resolve_code == 0 and resolve_log:
        first_line = resolve_log.splitlines()[0]
        parts = first_line.split("\t", 1)
        midas_result_out = Path(parts[0])
        midas_resolution_kind = parts[1] if len(parts) > 1 else midas_resolution_kind
    else:
        midas_result_out = (
            REPO_ROOT
            / "implementation/phase1/open_data/midas/midas_generator_33.optimized.midas_gen_same_mesh_result.json"
        )
    steps.append(
        {
            "step": "midas_same_mesh_result_resolve",
            "exit_code": resolve_code,
            "log": resolve_log,
            "resolution_kind": midas_resolution_kind,
        }
    )

    if midas_resolution_kind in {"missing", "default_proxy", "proxy_sibling"} and not skip_model_derived:
        code, log = _run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/build_midas_gen_same_mesh_result_proxy.py"),
                "--roundtrip-json",
                str(args.roundtrip_json),
                "--commercial-crossval-json",
                str(out_dir / "commercial_solver_cross_validation.json"),
                "--output-json",
                str(midas_result_out),
            ]
        )
        steps.append({"step": "midas_gen_same_mesh_result_proxy", "exit_code": code, "log": log})

    midas_validate_out = out_dir / "midas_gen_same_mesh_result_validation.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/validate_midas_gen_same_mesh_result.py"),
            "--result-json",
            str(midas_result_out),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(midas_validate_out),
        ]
    )
    steps.append({"step": "midas_gen_same_mesh_result_validation", "exit_code": code, "log": log})

    native_wind_lateral_out = out_dir / "mgt_real_section_lateral_pushover.json"
    wind_lateral_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/solve_mgt_real_section_lateral_pushover.py"),
        "--roundtrip-npz",
        str(args.roundtrip_json.with_suffix(".npz")),
        "--mgt-path",
        str(mgt_path),
        "--boundary",
        "both",
        "--output-json",
        str(native_wind_lateral_out),
    ]
    if track == "wind":
        code, log = _run(wind_lateral_cmd)
        steps.append({"step": "mgt_real_section_lateral_pushover", "exit_code": code, "log": log})
    else:
        native_wind_lateral_out = None

    midas_compare_out = out_dir / "midas_gen_same_mesh_native_comparison.json"
    compare_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_midas_gen_same_mesh_native_comparison.py"),
        "--result-json",
        str(midas_result_out),
        "--roundtrip-json",
        str(args.roundtrip_json),
        "--native-3d-solve-json",
        str(mgt_3d_out),
        "--native-condensed-solve-json",
        str(mgt_condensed_out),
        "--output-json",
        str(midas_compare_out),
    ]
    if track == "wind" and native_wind_lateral_out is not None:
        compare_cmd.extend(["--native-wind-lateral-json", str(native_wind_lateral_out)])
    code, log = _run(compare_cmd)
    steps.append({"step": "midas_gen_same_mesh_native_comparison", "exit_code": code, "log": log})

    gpu_equiv_out = out_dir / "gpu_production_newton_equivalence_gate.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_gpu_production_newton_equivalence_gate.py"),
            "--output-json",
            str(gpu_equiv_out),
        ]
    )
    steps.append({"step": "gpu_production_newton_equivalence_gate", "exit_code": code, "log": log})

    gpu_newton_cert_out = out_dir / "gpu_newton_terminal_certification.json"
    equiv_arg = ["--production-equivalence-json", str(gpu_equiv_out)] if gpu_equiv_out.is_file() else []
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_gpu_newton_terminal_certification.py"),
            "--output-json",
            str(gpu_newton_cert_out),
        ]
        + equiv_arg
    )
    steps.append({"step": "gpu_newton_terminal_certification", "exit_code": code, "log": log})

    gpu_claim_out = out_dir / "gpu_solver_claim_receipt.json"
    gpu_cert_arg = ["--terminal-certification-json", str(gpu_newton_cert_out)] if gpu_newton_cert_out.is_file() else []
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_gpu_solver_claim_receipt.py"),
            "--output-json",
            str(gpu_claim_out),
        ]
        + gpu_cert_arg
    )
    steps.append({"step": "gpu_solver_claim_receipt", "exit_code": code, "log": log})

    gpu_newton_checklist_out = out_dir / "gpu_newton_certification_checklist.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_gpu_newton_certification_checklist.py"),
            "--output-json",
            str(gpu_newton_checklist_out),
        ]
        + gpu_cert_arg
    )
    steps.append({"step": "gpu_newton_certification_checklist", "exit_code": code, "log": log})

    gpu_rocm_workstation_out = out_dir / "gpu_rocm_workstation_receipt.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rocm_workstation_gpu_receipt.py"),
            "--output-json",
            str(gpu_rocm_workstation_out),
        ]
    )
    steps.append({"step": "gpu_rocm_workstation_receipt", "exit_code": code, "log": log})

    mgt_rocm_sparse_probe_out = out_dir / "mgt_rocm_sparse_solver_probe.json"
    heavy_rocm_probe_execution_mode = (
        "rerun"
        if args.rerun_heavy_probes or args.rerun_heavy_rocm_probe or not mgt_rocm_sparse_probe_out.is_file()
        else "reuse_existing_receipt"
    )
    if args.rerun_heavy_probes or args.rerun_heavy_rocm_probe or not mgt_rocm_sparse_probe_out.is_file():
        code, log = _run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/run_mgt_rocm_sparse_solver_probe.py"),
                "--roundtrip-json",
                str(args.roundtrip_json),
                "--output-json",
                str(mgt_rocm_sparse_probe_out),
            ],
            timeout_seconds=step_timeout_seconds,
            force_rerun=True,
        )
        steps.append(
            {
                "step": "mgt_rocm_sparse_solver_probe",
                "exit_code": code,
                "log": log,
                "execution_mode": heavy_rocm_probe_execution_mode,
                "timeout_seconds": int(step_timeout_seconds),
            }
        )
    else:
        steps.append(
            {
                "step": "mgt_rocm_sparse_solver_probe",
                "exit_code": 0,
                "log": f"reused_existing_receipt={mgt_rocm_sparse_probe_out}",
                "execution_mode": "reuse_existing_receipt",
                "timeout_seconds": int(step_timeout_seconds),
                "claim_boundary": (
                    "Delivery bundling reuses the existing ROCm sparse probe receipt by default so the "
                    "evidence bundle stays bounded. Dedicated ROCm closure work must run "
                    "scripts/run_mgt_rocm_sparse_solver_probe.py explicitly."
                ),
            }
        )

    solver_runtime_backend_policy_out = out_dir / "solver_runtime_backend_policy.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_solver_runtime_backend_policy.py"),
            "--productization-dir",
            str(out_dir),
            "--output-json",
            str(solver_runtime_backend_policy_out),
        ]
    )
    steps.append({"step": "solver_runtime_backend_policy", "exit_code": code, "log": log})

    story_out = out_dir / "story_model_reanalysis.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_story_model_reanalysis.py"),
            "--state-npz",
            str(
                REPO_ROOT
                / "implementation/phase1/release/design_optimization/design_optimization_solver_loop_state.npz"
            ),
            "--changes-json",
            str(args.changes_json),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(story_out),
        ]
    )
    steps.append({"step": "story_model_reanalysis", "exit_code": code, "log": log})

    reanalysis_out = out_dir / "post_optimization_reanalysis_gate.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_post_optimization_reanalysis_gate.py"),
            "--optimized-roundtrip-json",
            str(args.roundtrip_json),
            "--changes-json",
            str(args.changes_json),
            "--output-json",
            str(reanalysis_out),
            "--require-changes",
            "--run-story-reanalysis",
            "--sync-mgt-provenance",
        ]
    )
    steps.append({"step": "post_optimization_reanalysis", "exit_code": code, "log": log})

    ai_decision_review_out = out_dir / "ai_decision_review_artifacts.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_decision_review_artifacts.py"),
            "--productization-dir",
            str(out_dir),
            "--output-json",
            str(ai_decision_review_out),
        ]
    )
    steps.append({"step": "ai_decision_review_artifacts", "exit_code": code, "log": log})

    ai_physics_guard_out = out_dir / "ai_physics_guard_execution.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_physics_guard_execution.py"),
            "--productization-dir",
            str(out_dir),
            "--output-json",
            str(ai_physics_guard_out),
        ]
    )
    steps.append({"step": "ai_physics_guard_execution", "exit_code": code, "log": log})

    ai_input_code_guard_out = out_dir / "ai_input_code_guard_artifacts.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_ai_input_code_guard_artifacts.py"),
            "--productization-dir",
            str(out_dir),
            "--roundtrip-json",
            str(args.roundtrip_json),
            "--output-json",
            str(ai_input_code_guard_out),
        ]
    )
    steps.append({"step": "ai_input_code_guard_artifacts", "exit_code": code, "log": log})

    kds_detailing_support_out = out_dir / "kds_detailing_support_matrix.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_kds_detailing_support_matrix.py"),
            "--productization-dir",
            str(out_dir),
            "--output-json",
            str(kds_detailing_support_out),
        ]
    )
    steps.append({"step": "kds_detailing_support_matrix", "exit_code": code, "log": log})

    optimization_audit_out = out_dir / "optimization_productization_audit.json"
    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_optimization_productization_audit.py"),
            "--productization-dir",
            str(out_dir),
            "--output-json",
            str(optimization_audit_out),
        ]
    )
    steps.append({"step": "optimization_productization_audit", "exit_code": code, "log": log})

    artifacts = {
        "commercial_cross_validation": str(crossval_out) if crossval_out.is_file() else "",
        "proxy_solver_divergence": str(proxy_out) if proxy_out.is_file() else "",
        "story_model_reanalysis": str(story_out) if story_out.is_file() else "",
        "gpu_solver_claim_receipt": str(gpu_claim_out) if gpu_claim_out.is_file() else "",
        "mgt_native_reanalysis_pipeline": str(mgt_pipeline_out) if mgt_pipeline_out.is_file() else "",
        "mgt_full_line_mesh_sparse_equilibrium": (
            str(mgt_full_line_sparse_out) if mgt_full_line_sparse_out.is_file() else ""
        ),
        "mgt_full_frame_6dof_sparse_equilibrium": (
            str(mgt_full_frame_6dof_out) if mgt_full_frame_6dof_out.is_file() else ""
        ),
        "mgt_pdelta_continuation_probe": (
            str(mgt_pdelta_continuation_out) if mgt_pdelta_continuation_out.is_file() else ""
        ),
        "mgt_coarsened_authored_support_pdelta_probe": (
            str(mgt_coarsened_authored_support_pdelta_out)
            if mgt_coarsened_authored_support_pdelta_out.is_file()
            else ""
        ),
        "mgt_uncoarsened_boundary_pdelta_probe": (
            str(mgt_uncoarsened_boundary_pdelta_out)
            if mgt_uncoarsened_boundary_pdelta_out.is_file()
            else ""
        ),
        "mgt_surface_membrane_tangent": (
            str(mgt_surface_membrane_out) if mgt_surface_membrane_out.is_file() else ""
        ),
        "mgt_surface_shell_bending_tangent": (
            str(mgt_surface_shell_bending_out) if mgt_surface_shell_bending_out.is_file() else ""
        ),
        "mgt_shell_calibration_benchmarks": (
            str(mgt_shell_calibration_out) if mgt_shell_calibration_out.is_file() else ""
        ),
        "mgt_coupled_frame_surface_sparse_equilibrium": (
            str(mgt_coupled_frame_surface_out) if mgt_coupled_frame_surface_out.is_file() else ""
        ),
        "mgt_coupled_frame_shell_sparse_equilibrium": (
            str(mgt_coupled_frame_shell_out) if mgt_coupled_frame_shell_out.is_file() else ""
        ),
        "mgt_native_modal_buckling_solver": (
            str(native_modal_buckling_out) if native_modal_buckling_out.is_file() else ""
        ),
        "mgt_global_fea_condensed_solve": str(mgt_condensed_out) if mgt_condensed_out.is_file() else "",
        "mgt_frame_material_nonlinear_tangent": (
            str(mgt_frame_material_nonlinear_out) if mgt_frame_material_nonlinear_out.is_file() else ""
        ),
        "material_element_tangent_support_matrix": (
            str(material_element_tangent_out) if material_element_tangent_out.is_file() else ""
        ),
        "mgt_beam_offset_support_receipt": (
            str(mgt_beam_offset_support_out) if mgt_beam_offset_support_out.is_file() else ""
        ),
        "mgt_element_local_axis_opening_semantics_receipt": (
            str(mgt_local_axis_opening_out) if mgt_local_axis_opening_out.is_file() else ""
        ),
        "mgt_boundary_entity_support_receipt": (
            str(mgt_boundary_entity_support_out) if mgt_boundary_entity_support_out.is_file() else ""
        ),
        "mgt_boundary_spring_tangent_receipt": (
            str(mgt_boundary_spring_tangent_out) if mgt_boundary_spring_tangent_out.is_file() else ""
        ),
        "mgt_uncoarsened_boundary_global_equilibrium": (
            str(mgt_uncoarsened_boundary_global_out)
            if mgt_uncoarsened_boundary_global_out.is_file()
            else ""
        ),
        "mgt_story_eccentricity_load_receipt": (
            str(mgt_story_eccentricity_load_out) if mgt_story_eccentricity_load_out.is_file() else ""
        ),
        "mgt_coupled_frame_shell_story_eccentricity_equilibrium": (
            str(mgt_coupled_frame_shell_story_eccentricity_out)
            if mgt_coupled_frame_shell_story_eccentricity_out.is_file()
            else ""
        ),
        "load_stage_runtime_flow_receipt": (
            str(load_stage_runtime_flow_out) if load_stage_runtime_flow_out.is_file() else ""
        ),
        "gpu_newton_terminal_certification": str(gpu_newton_cert_out) if gpu_newton_cert_out.is_file() else "",
        "gpu_rocm_workstation_receipt": str(gpu_rocm_workstation_out) if gpu_rocm_workstation_out.is_file() else "",
        "solver_runtime_backend_policy": (
            str(solver_runtime_backend_policy_out)
            if solver_runtime_backend_policy_out.is_file()
            else ""
        ),
        "mgt_rocm_sparse_solver_probe": (
            str(mgt_rocm_sparse_probe_out) if mgt_rocm_sparse_probe_out.is_file() else ""
        ),
        "post_optimization_reanalysis": str(reanalysis_out) if reanalysis_out.is_file() else "",
        "ai_decision_review_artifacts": str(ai_decision_review_out) if ai_decision_review_out.is_file() else "",
        "ml_surrogate_checkpoint_manifest": str(ml_checkpoint_manifest_out) if ml_checkpoint_manifest_out.is_file() else "",
        "kds_detailing_support_matrix": str(kds_detailing_support_out) if kds_detailing_support_out.is_file() else "",
        "mgt_roundtrip_sync": str(sync_out) if sync_out.is_file() else "",
        "mgt_global_fea_readiness": str(global_fea_out) if global_fea_out.is_file() else "",
        "rh_closure_checklist": str(rh_checklist_out) if rh_checklist_out.is_file() else "",
        "changes_json": str(args.changes_json),
    }

    def _load(path: Path) -> dict:
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    crossval = _load(crossval_out)
    proxy = _load(proxy_out)
    story_payload = _load(story_out)
    story_receipt = story_payload.get("story_model_reanalysis") if isinstance(story_payload, dict) else {}
    mgt_pipeline = _load(mgt_pipeline_out)
    global_fea = _load(global_fea_out)
    reanalysis = _load(reanalysis_out)
    solver_backend_policy = _load(solver_runtime_backend_policy_out)
    changes = _load(args.changes_json)
    alignment = changes.get("member_alignment") if isinstance(changes.get("member_alignment"), dict) else {}

    blockers: list[str] = []
    if mesh_contract_exit != 0:
        blockers.append("mgt_mesh_contract_blocked")
    crossval_ok_statuses = {"pass", "partial", "pass_with_marginal_metrics", "partial_marginal_only"}
    if crossval.get("status") not in crossval_ok_statuses:
        blockers.append("commercial_cross_validation_not_pass")
    if int(crossval.get("metric_failures_hard") or 0) > 0:
        blockers.append("commercial_cross_validation_hard_failures")
    if global_fea.get("status") == "blocked":
        blockers.append("mgt_global_fea_readiness_blocked")
    if proxy.get("divergence_count", 0) > 0:
        blockers.append("proxy_solver_divergence_present")
    if reanalysis.get("blockers"):
        blockers.extend(str(item) for item in reanalysis.get("blockers") or [])

    bundle = {
        "schema_version": "delivery-evidence-bundle.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if not blockers else "review_required",
        "claim": "Engineer-in-loop delivery evidence bundle; not permit approval.",
        "steps": steps,
        "artifacts": artifacts,
        "summary": {
            "cross_validation_status": crossval.get("status"),
            "cross_validation_marginal_accepted": crossval.get("metric_marginal_accepted"),
            "cross_validation_hard_failures": crossval.get("metric_failures_hard"),
            "mgt_roundtrip_sync_status": _load(sync_out).get("status") if sync_out.is_file() else "",
            "mgt_roundtrip_parsed": bool((_load(sync_out).get("parse") or {}).get("contract_pass")),
            "global_fea_readiness_status": global_fea.get("status"),
            "global_fea_readiness_ready": global_fea.get("readiness_for_global_fea_wiring"),
            "proxy_divergence_count": proxy.get("divergence_count"),
            "reanalysis_status": reanalysis.get("status"),
            "story_reanalysis_status": story_receipt.get("status"),
            "mgt_pipeline_status": mgt_pipeline.get("status"),
            "native_fea_solve_status": ((mgt_pipeline.get("native_fea") or {}).get("native_solve_status")),
            "mgt_condensed_solve_status": _load(mgt_condensed_out).get("native_solve_status"),
            "mgt_integrity_status": (mgt_pipeline.get("mgt_integrity") or {}).get("integrity_status"),
            "official_solver_compute_backend": solver_backend_policy.get("official_solver_compute_backend"),
            "official_solver_backend": solver_backend_policy.get("official_solver_backend"),
            "official_solver_backend_family": solver_backend_policy.get(
                "official_solver_backend_family"
            ),
            "gpu_required_for_commercial_solver_closure": solver_backend_policy.get(
                "gpu_required_for_commercial_solver_closure"
            ),
            "torch_device_label_is_pytorch_rocm_compat_alias": solver_backend_policy.get(
                "torch_device_label_is_pytorch_rocm_compat_alias"
            ),
            "cpu_diagnostic_promotes_solver_closure": solver_backend_policy.get(
                "cpu_diagnostic_promotes_solver_closure"
            ),
            "cpu_solver_fallback_detected": solver_backend_policy.get(
                "cpu_solver_fallback_detected"
            ),
            "cpu_fallback_allowed_for_official_solver_closure": solver_backend_policy.get(
                "cpu_fallback_allowed_for_official_solver_closure"
            ),
            "step_timeout_seconds": int(step_timeout_seconds),
            "heavy_rocm_probe_execution_mode": heavy_rocm_probe_execution_mode,
            "heavy_probe_reuse_policy": (
                "delivery bundle reuses existing heavy nonlinear/GPU receipts unless "
                "--rerun-heavy-probes or --rerun-heavy-rocm-probe is explicit"
            ),
            "member_alignment_status": alignment.get("alignment_status"),
            "removed_member_count": len(alignment.get("removed_member_ids") or []),
        },
        "blockers": blockers,
        "holdout_evidence_hints": {
            "RH-002": {
                "supplementary_artifact": str(crossval_out),
                "note": "Commercial HF/LF cross-validation supports legacy-tool comparison workflow.",
            },
            "RH-001": {
                "supplementary_artifact": str(reanalysis_out),
                "note": "Post-optimization reanalysis gate records story-proxy safety metrics.",
            },
            "RH-003": {
                "supplementary_artifact": str(story_out),
                "note": "Story-model reanalysis receipt with MGT provenance for authority workflow review.",
            },
        },
    }
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_closure_checklist.py"),
            "--rh-json",
            str(rh_path),
            "--bundle-json",
            str(args.output_json),
            "--output-json",
            str(rh_checklist_out),
        ]
    )
    steps.append({"step": "rh_closure_checklist", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_signed_closure_packet_template.py"),
            "--rh-json",
            str(rh_path),
            "--checklist-json",
            str(rh_checklist_out),
            "--output-json",
            str(rh_template_out),
        ]
    )
    steps.append({"step": "rh_signed_closure_packet_template", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_engineer_review_packet_html.py"),
            "--template-json",
            str(rh_template_out),
            "--bundle-json",
            str(args.output_json),
            "--output-html",
            str(rh_html_out),
        ]
    )
    steps.append({"step": "rh_engineer_review_packet_html", "exit_code": code, "log": log})

    bundle["steps"] = steps
    bundle["artifacts"]["rh_closure_checklist"] = str(rh_checklist_out) if rh_checklist_out.is_file() else ""
    bundle["artifacts"]["rh_signed_closure_packet_template"] = (
        str(rh_template_out) if rh_template_out.is_file() else ""
    )
    bundle["artifacts"]["gpu_newton_certification_checklist"] = (
        str(gpu_newton_checklist_out) if gpu_newton_checklist_out.is_file() else ""
    )
    bundle["artifacts"]["gpu_newton_terminal_certification"] = (
        str(gpu_newton_cert_out) if gpu_newton_cert_out.is_file() else ""
    )
    bundle["artifacts"]["gpu_rocm_workstation_receipt"] = (
        str(gpu_rocm_workstation_out) if gpu_rocm_workstation_out.is_file() else ""
    )
    bundle["artifacts"]["solver_runtime_backend_policy"] = (
        str(solver_runtime_backend_policy_out)
        if solver_runtime_backend_policy_out.is_file()
        else ""
    )
    bundle["artifacts"]["mgt_rocm_sparse_solver_probe"] = (
        str(mgt_rocm_sparse_probe_out) if mgt_rocm_sparse_probe_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_global_fea_condensed_solve"] = (
        str(mgt_condensed_out) if mgt_condensed_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_global_fea_3d_native_solve"] = str(mgt_3d_out) if mgt_3d_out.is_file() else ""
    bundle["artifacts"]["mgt_full_line_mesh_sparse_equilibrium"] = (
        str(mgt_full_line_sparse_out) if mgt_full_line_sparse_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_full_frame_6dof_sparse_equilibrium"] = (
        str(mgt_full_frame_6dof_out) if mgt_full_frame_6dof_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_pdelta_continuation_probe"] = (
        str(mgt_pdelta_continuation_out) if mgt_pdelta_continuation_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_coarsened_authored_support_pdelta_probe"] = (
        str(mgt_coarsened_authored_support_pdelta_out)
        if mgt_coarsened_authored_support_pdelta_out.is_file()
        else ""
    )
    bundle["artifacts"]["mgt_uncoarsened_boundary_pdelta_probe"] = (
        str(mgt_uncoarsened_boundary_pdelta_out)
        if mgt_uncoarsened_boundary_pdelta_out.is_file()
        else ""
    )
    bundle["artifacts"]["mgt_frame_material_nonlinear_tangent"] = (
        str(mgt_frame_material_nonlinear_out) if mgt_frame_material_nonlinear_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_surface_membrane_tangent"] = (
        str(mgt_surface_membrane_out) if mgt_surface_membrane_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_surface_shell_bending_tangent"] = (
        str(mgt_surface_shell_bending_out) if mgt_surface_shell_bending_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_shell_calibration_benchmarks"] = (
        str(mgt_shell_calibration_out) if mgt_shell_calibration_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_coupled_frame_surface_sparse_equilibrium"] = (
        str(mgt_coupled_frame_surface_out) if mgt_coupled_frame_surface_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_coupled_frame_shell_sparse_equilibrium"] = (
        str(mgt_coupled_frame_shell_out) if mgt_coupled_frame_shell_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_native_modal_buckling_solver"] = (
        str(native_modal_buckling_out) if native_modal_buckling_out.is_file() else ""
    )
    bundle["artifacts"]["gpu_production_newton_equivalence_gate"] = (
        str(gpu_equiv_out) if gpu_equiv_out.is_file() else ""
    )
    bundle["artifacts"]["residual_holdout_closure_updates"] = str(rh_path) if rh_path.is_file() else ""
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/sync_holdout_supplementary_evidence.py"),
            "--bundle-json",
            str(args.output_json),
            "--residual-holdout-json",
            str(rh_path),
            "--output-json",
            str(rh_path),
        ]
    )
    steps.append({"step": "sync_holdout_supplementary", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/finalize_rh_signed_closure.py"),
            "--bundle-json",
            str(args.output_json),
            "--rh-json",
            str(rh_path),
            "--packet-dir",
            str(rh_packet_dir),
            "--output-json",
            str(rh_path),
        ]
    )
    steps.append({"step": "finalize_rh_signed_closure", "exit_code": code, "log": log})

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_rh_closure_checklist.py"),
            "--rh-json",
            str(rh_path),
            "--bundle-json",
            str(args.output_json),
            "--output-json",
            str(rh_checklist_out),
        ]
    )
    steps.append({"step": "rh_closure_checklist_post_sign", "exit_code": code, "log": log})

    bundle["steps"] = steps
    bundle["artifacts"]["rh_closure_checklist"] = str(rh_checklist_out) if rh_checklist_out.is_file() else ""
    rh_closed = _load(rh_path).get("rh_closure_status") == "closed"
    if not rh_closed:
        blockers.append("rh_signed_closure_incomplete")
    mesh_3d_status = _load(mgt_3d_out).get("native_solve_status")
    mgt_full_line_sparse = _load(mgt_full_line_sparse_out)
    if mgt_full_line_sparse.get("status") != "ready":
        blockers.append("mgt_full_line_mesh_sparse_equilibrium_not_ready")
    mgt_full_frame_6dof = _load(mgt_full_frame_6dof_out)
    if mgt_full_frame_6dof.get("status") != "ready":
        blockers.append("mgt_full_frame_6dof_sparse_equilibrium_not_ready")
    mgt_surface_membrane = _load(mgt_surface_membrane_out)
    if mgt_surface_membrane.get("status") != "ready":
        blockers.append("mgt_surface_membrane_tangent_not_ready")
    mgt_surface_shell_bending = _load(mgt_surface_shell_bending_out)
    if mgt_surface_shell_bending.get("status") != "ready":
        blockers.append("mgt_surface_shell_bending_tangent_not_ready")
    mgt_shell_calibration = _load(mgt_shell_calibration_out)
    if mgt_shell_calibration.get("status") != "ready":
        blockers.append("mgt_shell_calibration_benchmarks_not_ready")
    mgt_coupled_frame_surface = _load(mgt_coupled_frame_surface_out)
    if mgt_coupled_frame_surface.get("status") != "ready":
        blockers.append("mgt_coupled_frame_surface_sparse_equilibrium_not_ready")
    mgt_coupled_frame_shell = _load(mgt_coupled_frame_shell_out)
    if mgt_coupled_frame_shell.get("status") != "ready":
        blockers.append("mgt_coupled_frame_shell_sparse_equilibrium_not_ready")
    full_sparse_delivery_solve_ready = bool(
        mgt_full_line_sparse.get("status") == "ready"
        and mgt_full_frame_6dof.get("status") == "ready"
        and mgt_coupled_frame_shell.get("status") == "ready"
    )
    legacy_native_3d_ready = mesh_3d_status in {
        "mesh_3d_beam_global_wired",
        "mesh_3d_beam_global_wired_with_licensed_fingerprint_bridge",
    }
    if not legacy_native_3d_ready and not full_sparse_delivery_solve_ready:
        blockers.append("mgt_global_fea_3d_native_solve_not_wired")
    condensed_status = _load(mgt_condensed_out).get("native_solve_status")
    if condensed_status != "condensed_global_fea_wired" and not full_sparse_delivery_solve_ready:
        blockers.append("mgt_global_fea_condensed_solve_not_wired")
    bundle["summary"]["delivery_solve_basis"] = (
        "legacy_native_and_condensed"
        if legacy_native_3d_ready and condensed_status == "condensed_global_fea_wired"
        else "current_full_sparse_line_frame_coupled_evidence"
        if full_sparse_delivery_solve_ready
        else "insufficient_solver_evidence"
    )
    mgt_frame_material_nonlinear = _load(mgt_frame_material_nonlinear_out)
    if mgt_frame_material_nonlinear.get("status") != "ready":
        blockers.append("mgt_frame_material_nonlinear_tangent_not_ready")
    native_modal_buckling = _load(native_modal_buckling_out)
    if native_modal_buckling.get("status") != "ready":
        blockers.append("mgt_native_modal_buckling_solver_not_ready")
    load_stage_runtime_flow = _load(load_stage_runtime_flow_out)
    if load_stage_runtime_flow.get("status") != "ready":
        blockers.append("load_stage_runtime_flow_receipt_not_ready")
    material_element_tangent = _load(material_element_tangent_out)
    if material_element_tangent.get("status") != "ready":
        blockers.append("material_element_tangent_support_matrix_not_ready")
    kds_detailing_support = _load(kds_detailing_support_out)
    if kds_detailing_support.get("status") != "ready":
        blockers.append("kds_detailing_support_matrix_not_ready")
    gpu_equiv = _load(gpu_equiv_out)
    if not gpu_equiv.get("production_newton_equivalent_to_closed_form"):
        blockers.append("gpu_production_newton_not_equivalent")
    gpu_cert = _load(gpu_newton_cert_out)
    if not gpu_cert.get("gpu_newton_terminal_proven"):
        blockers.append("gpu_newton_terminal_not_certified")
    bundle["status"] = "ready" if not blockers else "review_required"
    bundle["blockers"] = blockers
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    # Run ledger/governance snapshots twice on purpose: this first pass feeds
    # validation with the bundle/blocker state above, and the final pass below
    # republishes ledgers after validation writes its own receipt. Keep the
    # productization directory explicit so custom output runs never read the
    # scripts' default evidence directory by accident.
    commercial_gap_status_out = out_dir / "commercial_gap_ledger_status.json"
    code, log = _run(
        build_productization_status_command(
            "report_commercial_gap_ledger_status.py",
            productization_dir=out_dir,
            output_json=commercial_gap_status_out,
        )
    )
    steps.append({"step": "commercial_gap_ledger_status", "exit_code": code, "log": log})

    gap_status_out = out_dir / "gap_closure_status.json"
    code, log = _run(
        build_productization_status_command(
            "report_gap_closure_status.py",
            productization_dir=out_dir,
            output_json=gap_status_out,
        )
    )
    steps.append({"step": "gap_closure_status", "exit_code": code, "log": log})

    bundle["steps"] = steps
    bundle["artifacts"]["commercial_gap_ledger_status"] = (
        str(commercial_gap_status_out) if commercial_gap_status_out.is_file() else ""
    )
    bundle["artifacts"]["gap_closure_status"] = str(gap_status_out) if gap_status_out.is_file() else ""
    bundle["artifacts"]["mgt_roundtrip_assembly_fingerprint"] = (
        str(mgt_fingerprint_out) if mgt_fingerprint_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_global_fea_mesh_contract"] = (
        str(mgt_mesh_contract_out) if mgt_mesh_contract_out.is_file() else ""
    )
    bundle["artifacts"]["rh_engineer_review_packet_html"] = str(rh_html_out) if rh_html_out.is_file() else ""
    bundle["artifacts"]["ml_multi_objective_status"] = str(ml_status_out) if ml_status_out.is_file() else ""
    bundle["artifacts"]["load_combination_engine_gate"] = str(loadcomb_gate_out) if loadcomb_gate_out.is_file() else ""
    bundle["artifacts"]["load_stage_semantics_contract"] = (
        str(load_stage_contract_out) if load_stage_contract_out.is_file() else ""
    )
    bundle["artifacts"]["load_stage_runtime_flow_receipt"] = (
        str(load_stage_runtime_flow_out) if load_stage_runtime_flow_out.is_file() else ""
    )
    bundle["artifacts"]["material_element_tangent_support_matrix"] = (
        str(material_element_tangent_out) if material_element_tangent_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_beam_offset_support_receipt"] = (
        str(mgt_beam_offset_support_out) if mgt_beam_offset_support_out.is_file() else ""
    )
    bundle["artifacts"]["mgt_element_local_axis_opening_semantics_receipt"] = (
        str(mgt_local_axis_opening_out) if mgt_local_axis_opening_out.is_file() else ""
    )
    bundle["artifacts"]["ai_engine_productization_contracts"] = (
        str(ai_engine_contracts_out) if ai_engine_contracts_out.is_file() else ""
    )
    bundle["artifacts"]["ai_decision_review_artifacts"] = (
        str(ai_decision_review_out) if ai_decision_review_out.is_file() else ""
    )
    bundle["artifacts"]["ai_physics_guard_execution"] = (
        str(ai_physics_guard_out) if ai_physics_guard_out.is_file() else ""
    )
    bundle["artifacts"]["optimization_productization_audit"] = (
        str(optimization_audit_out) if optimization_audit_out.is_file() else ""
    )
    bundle["artifacts"]["ai_input_code_guard_artifacts"] = (
        str(ai_input_code_guard_out) if ai_input_code_guard_out.is_file() else ""
    )
    bundle["artifacts"]["kds_detailing_support_matrix"] = (
        str(kds_detailing_support_out) if kds_detailing_support_out.is_file() else ""
    )

    solver_governance_out = out_dir / "solver_governance_support_contract.json"
    code, log = _run(
        build_productization_status_command(
            "build_solver_governance_support_contract.py",
            productization_dir=out_dir,
            output_json=solver_governance_out,
        )
    )
    steps.append({"step": "solver_governance_support_contract", "exit_code": code, "log": log})
    bundle["artifacts"]["solver_governance_support_contract"] = (
        str(solver_governance_out) if solver_governance_out.is_file() else ""
    )
    bundle["status"] = "ready" if not blockers else "review_required"
    bundle["blockers"] = blockers
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    code, log = _run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/validate_productization_delivery_evidence.py"),
            "--productization-dir",
            str(out_dir),
            "--output-json",
            str(productization_validate_out),
        ]
    )
    steps.append({"step": "productization_delivery_evidence_validation", "exit_code": code, "log": log})
    if code != 0 and "productization_validation_failed" not in blockers:
        blockers.append("productization_validation_failed")
        bundle["status"] = "review_required"
        bundle["blockers"] = blockers
        args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    bundle["artifacts"]["productization_delivery_evidence_validation"] = (
        str(productization_validate_out) if productization_validate_out.is_file() else ""
    )

    # Validation writes a new artifact and may alter final blocker state, so
    # rebuild governance/status artifacts once more for the final published bundle.
    code, log = _run(
        build_productization_status_command(
            "build_solver_governance_support_contract.py",
            productization_dir=out_dir,
            output_json=solver_governance_out,
        )
    )
    steps.append({"step": "solver_governance_support_contract_final", "exit_code": code, "log": log})

    code, log = _run(
        build_productization_status_command(
            "report_commercial_gap_ledger_status.py",
            productization_dir=out_dir,
            output_json=commercial_gap_status_out,
        )
    )
    steps.append({"step": "commercial_gap_ledger_status_final", "exit_code": code, "log": log})

    code, log = _run(
        build_productization_status_command(
            "report_gap_closure_status.py",
            productization_dir=out_dir,
            output_json=gap_status_out,
        )
    )
    steps.append({"step": "gap_closure_status_final", "exit_code": code, "log": log})
    bundle["steps"] = steps
    args.output_json.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(f"bundle: {bundle['status']} -> {args.output_json}")
    if blockers:
        print(f"bundle: blockers={','.join(blockers)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
