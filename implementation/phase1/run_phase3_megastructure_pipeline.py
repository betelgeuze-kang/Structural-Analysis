#!/usr/bin/env python3
"""Run phase3 mega-structure hardening pipeline with strict gates.

Pipeline:
1) Open source conversion (with provenance manifest)
2) Top-k benchmark contract
3) Adaptive-Newton noise convergence gate
4) Partitioned scaleout gate (PR/Nightly mode)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "phase3 megastructure pipeline passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_CONVERSION_FAIL": "open megastructure conversion failed",
    "ERR_DIVERSITY_FAIL": "building case diversity gate failed",
    "ERR_REAL_SOURCE_FAIL": "real-source integrity validation failed",
    "ERR_MIDAS_MGT_FAIL": "midas .mgt parsing/coarsening gate failed",
    "ERR_BENCHMARK_FAIL": "top-k benchmark failed",
    "ERR_NOISE_CONVERGENCE_FAIL": "adaptive-newton noise convergence gate failed",
    "ERR_PARTITION_SCALE_FAIL": "partitioned scaleout gate failed",
    "ERR_TOPOLOGY_FAIL": "opensees topology gate failed",
    "ERR_SYNC_STRESS_FAIL": "virtual sync stress gate failed",
    "ERR_GPU_STRICT_FAIL": "gpu strict gate failed",
    "ERR_NIGHTLY_10M_FAIL": "nightly 10M scale gate failed",
    "ERR_SUMMARY_FAIL": "summary validation failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "catalog",
        "candidate_id",
        "input_path",
        "summary_out",
        "benchmark_epochs",
        "benchmark_branches",
        "benchmark_top_k",
        "benchmark_target_split",
        "ci_mode",
    ],
    "properties": {
        "catalog": {"type": "string", "minLength": 1},
        "candidate_id": {"type": "string", "minLength": 1},
        "input_path": {"type": "string", "minLength": 1},
        "download_if_missing": {"type": "boolean"},

        "conversion_report": {"type": "string", "minLength": 1},
        "source_manifest_report": {"type": "string", "minLength": 1},
        "dynamic_out": {"type": "string", "minLength": 1},
        "opensees_model": {"type": "string", "minLength": 1},
        "mgt_model": {"type": "string"},
        "mgt_report_out": {"type": "string", "minLength": 1},
        "mgt_json_out": {"type": "string", "minLength": 1},
        "mgt_npz_out": {"type": "string", "minLength": 1},
        "mgt_edge_list_out": {"type": "string", "minLength": 1},
        "prefer_mgt_for_partition": {"type": "boolean"},
        "topology_report_out": {"type": "string", "minLength": 1},
        "topology_edges_out": {"type": "string", "minLength": 1},
        "topology_csr_out": {"type": "string", "minLength": 1},
        "benchmark_cases_out": {"type": "string", "minLength": 1},
        "benchmark_out": {"type": "string", "minLength": 1},
        "comparison_out": {"type": "string", "minLength": 1},
        "noise_convergence_out": {"type": "string", "minLength": 1},
        "partitioned_scaleout_out": {"type": "string", "minLength": 1},
        "sync_stress_out": {"type": "string", "minLength": 1},
        "sync_inline_ground_motion_csv": {"type": "string", "minLength": 1},
        "sync_inline_max_steps": {"type": "integer", "minimum": 10},
        "summary_out": {"type": "string", "minLength": 1},

        "benchmark_epochs": {"type": "integer", "minimum": 1},
        "benchmark_branches": {"type": "integer", "minimum": 2},
        "benchmark_top_k": {"type": "integer", "minimum": 2},
        "benchmark_target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "max_drift_error_pct": {"type": "number", "minimum": 0.0},
        "max_base_shear_error_pct": {"type": "number", "minimum": 0.0},
        "min_mode_shape_mac": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_buckling_factor_error_pct": {"type": "number", "minimum": 0.0},

        "require_real_source": {"type": "boolean"},
        "require_real_topology": {"type": "boolean"},
        "require_shell_beam_mix": {"type": "boolean"},
        "require_case_diversity": {"type": "boolean"},
        "min_topology_types": {"type": "integer", "minimum": 1},
        "min_hazard_types": {"type": "integer", "minimum": 1},
        "min_material_types": {"type": "integer", "minimum": 1},
        "allow_sanity_sample": {"type": "boolean"},
        "gpu_strict": {"type": "boolean"},

        "ci_mode": {"type": "string", "enum": ["pr", "nightly"]},
        "scale_levels_pr": {"type": "string", "minLength": 1},
        "scale_levels_nightly": {"type": "string", "minLength": 1},
        "partition_max_projection_ratio": {"type": "number", "minimum": 0.0},
        "partition_edge_cut_ratio_max": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "partition_halo_node_ratio_max": {"type": "number", "minimum": 0.0, "maximum": 1.0},

        "noise_seeds": {"type": "string", "minLength": 1},
        "noise_stiffness_levels_pct": {"type": "string", "minLength": 1},
        "noise_stage_thresholds_pct": {"type": "string", "minLength": 1},
        "noise_limit_cases": {"type": "integer", "minimum": 1},
        "noise_target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "noise_min_topology_types": {"type": "integer", "minimum": 1},
        "noise_min_hazard_types": {"type": "integer", "minimum": 1},
        "noise_min_seed_count": {"type": "integer", "minimum": 3},
        "noise_stagewise_execution": {"type": "boolean"},
        "noise_stop_on_stage_fail": {"type": "boolean"},

        "allow_cpu_required": {"type": "boolean"},
    },
}

RUN_ENV_OVERRIDES: dict[str, str] = {}


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run(step: str, cmd: list[str], logs: list[dict]) -> bool:
    t0 = time.time()
    proc = subprocess.run(cmd, text=True, capture_output=True, env={**os.environ, **RUN_ENV_OVERRIDES})
    dt = time.time() - t0
    logs.append(
        {
            "step": step,
            "seconds": float(dt),
            "command": shlex.join(cmd),
            "return_code": int(proc.returncode),
            "stdout_tail": (proc.stdout or "")[-1600:],
            "stderr_tail": (proc.stderr or "")[-1600:],
        }
    )
    return proc.returncode == 0


def _load_catalog_recommended(catalog_path: Path) -> tuple[str, str]:
    if not catalog_path.exists():
        return "zenodo_atwood_highrise_shm_2025", "opstool_606m_megatall_model"
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        rec = payload.get("recommended_phase3_substitute", {})
        return str(rec.get("primary", "zenodo_atwood_highrise_shm_2025")), str(
            rec.get("secondary", "opstool_606m_megatall_model")
        )
    except Exception:
        return "zenodo_atwood_highrise_shm_2025", "opstool_606m_megatall_model"


def _archive_outputs(test_name: str, paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name=test_name,
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    logger = get_logger("phase1.run_phase3_megastructure_pipeline")
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", default="implementation/phase1/open_data/megastructure/mega_structure_catalog.json")
    p.add_argument("--candidate-id", default="")
    p.add_argument("--input-path", default="implementation/phase1/open_data/megastructure")
    p.add_argument("--download-if-missing", action="store_true")

    p.add_argument("--conversion-report", default="implementation/phase1/open_data/megastructure/atwood_conversion_report.json")
    p.add_argument("--source-manifest-report", default="implementation/phase1/open_data/megastructure/atwood_conversion_report.source_manifest.json")
    p.add_argument("--dynamic-out", default="implementation/phase1/spatiotemporal_data/atwood_dynamic_cases.jsonl")
    p.add_argument("--opensees-model", default="implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl")
    p.add_argument("--mgt-model", default="")
    p.add_argument("--mgt-report-out", default="implementation/phase1/midas_mgt_conversion_report.json")
    p.add_argument("--mgt-json-out", default="implementation/phase1/open_data/midas/midas_model.json")
    p.add_argument("--mgt-npz-out", default="implementation/phase1/open_data/midas/midas_graph.npz")
    p.add_argument("--mgt-edge-list-out", default="implementation/phase1/open_data/midas/midas_edge_list.json")
    p.add_argument("--prefer-mgt-for-partition", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--topology-report-out", default="implementation/phase1/opensees_topology_report.json")
    p.add_argument("--topology-edges-out", default="implementation/phase1/open_data/megastructure/opensees_edges.json")
    p.add_argument("--topology-csr-out", default="implementation/phase1/open_data/megastructure/opensees_csr.npz")
    p.add_argument("--benchmark-cases-out", default="implementation/phase1/commercial_benchmark_cases.atwood_open.json")
    p.add_argument("--benchmark-out", default="implementation/phase1/hf_benchmark_report.atwood_open.json")
    p.add_argument("--comparison-out", default="implementation/phase1/topk_comparison_experiment_report.atwood_open.json")
    p.add_argument("--noise-convergence-out", default="implementation/phase1/noise_convergence_gate_report.json")
    p.add_argument("--partitioned-scaleout-out", default="implementation/phase1/partitioned_scaleout_report.json")
    p.add_argument("--sync-stress-out", default="implementation/phase1/sync_stress_gate_report.json")
    p.add_argument("--sync-inline-ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--sync-inline-max-steps", type=int, default=800)
    p.add_argument("--summary-out", default="implementation/phase1/phase3_megastructure_pipeline_report.json")

    p.add_argument("--benchmark-epochs", type=int, default=160)
    p.add_argument("--benchmark-branches", type=int, default=10)
    p.add_argument("--benchmark-top-k", type=int, default=3)
    p.add_argument("--benchmark-lr", type=float, default=0.055)
    p.add_argument("--benchmark-epsilon", type=float, default=0.11)
    p.add_argument("--benchmark-temperature", type=float, default=0.32)
    p.add_argument("--benchmark-seed", type=int, default=23)
    p.add_argument("--benchmark-target-split", choices=["all", "train", "val", "test"], default="test")
    p.add_argument("--max-drift-error-pct", type=float, default=5.0)
    p.add_argument("--max-base-shear-error-pct", type=float, default=5.0)
    p.add_argument("--min-mode-shape-mac", type=float, default=0.85)
    p.add_argument("--max-buckling-factor-error-pct", type=float, default=5.0)

    p.add_argument("--require-real-source", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-real-topology", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-shell-beam-mix", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-case-diversity", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--min-topology-types", type=int, default=3)
    p.add_argument("--min-hazard-types", type=int, default=2)
    p.add_argument("--min-material-types", type=int, default=2)
    p.add_argument("--allow-sanity-sample", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--gpu-strict", action=argparse.BooleanOptionalAction, default=True)

    p.add_argument("--ci-mode", choices=["pr", "nightly"], default="pr")
    p.add_argument("--scale-levels-pr", default="1000000,3000000")
    p.add_argument("--scale-levels-nightly", default="1000000,3000000,10000000")
    p.add_argument("--partition-max-projection-ratio", type=float, default=2000.0)
    p.add_argument("--partition-edge-cut-ratio-max", type=float, default=0.12)
    p.add_argument("--partition-halo-node-ratio-max", type=float, default=0.18)

    p.add_argument("--noise-seeds", default="7,11,19,23,31,47,59")
    p.add_argument("--noise-stiffness-levels-pct", default="5,10")
    p.add_argument("--noise-stage-thresholds-pct", default="0,5,10")
    p.add_argument("--noise-limit-cases", type=int, default=12)
    p.add_argument("--noise-target-split", choices=["all", "train", "val", "test"], default="all")
    p.add_argument("--noise-min-topology-types", type=int, default=2)
    p.add_argument("--noise-min-hazard-types", type=int, default=2)
    p.add_argument("--noise-min-seed-count", type=int, default=3)
    p.add_argument("--noise-stagewise-execution", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--noise-stop-on-stage-fail", action=argparse.BooleanOptionalAction, default=True)

    p.add_argument("--allow-cpu-required", action="store_true")
    args = p.parse_args()

    primary, secondary = _load_catalog_recommended(Path(args.catalog))
    candidate_id = str(args.candidate_id).strip() or primary

    input_payload = {
        "catalog": str(args.catalog),
        "candidate_id": candidate_id,
        "input_path": str(args.input_path),
        "download_if_missing": bool(args.download_if_missing),
        "conversion_report": str(args.conversion_report),
        "source_manifest_report": str(args.source_manifest_report),
        "dynamic_out": str(args.dynamic_out),
        "opensees_model": str(args.opensees_model),
        "mgt_model": str(args.mgt_model),
        "mgt_report_out": str(args.mgt_report_out),
        "mgt_json_out": str(args.mgt_json_out),
        "mgt_npz_out": str(args.mgt_npz_out),
        "mgt_edge_list_out": str(args.mgt_edge_list_out),
        "prefer_mgt_for_partition": bool(args.prefer_mgt_for_partition),
        "topology_report_out": str(args.topology_report_out),
        "topology_edges_out": str(args.topology_edges_out),
        "topology_csr_out": str(args.topology_csr_out),
        "benchmark_cases_out": str(args.benchmark_cases_out),
        "benchmark_out": str(args.benchmark_out),
        "comparison_out": str(args.comparison_out),
        "noise_convergence_out": str(args.noise_convergence_out),
        "partitioned_scaleout_out": str(args.partitioned_scaleout_out),
        "sync_stress_out": str(args.sync_stress_out),
        "sync_inline_ground_motion_csv": str(args.sync_inline_ground_motion_csv),
        "sync_inline_max_steps": int(args.sync_inline_max_steps),
        "summary_out": str(args.summary_out),
        "benchmark_epochs": int(args.benchmark_epochs),
        "benchmark_branches": int(args.benchmark_branches),
        "benchmark_top_k": int(args.benchmark_top_k),
        "benchmark_target_split": str(args.benchmark_target_split),
        "max_drift_error_pct": float(args.max_drift_error_pct),
        "max_base_shear_error_pct": float(args.max_base_shear_error_pct),
        "min_mode_shape_mac": float(args.min_mode_shape_mac),
        "max_buckling_factor_error_pct": float(args.max_buckling_factor_error_pct),
        "require_real_source": bool(args.require_real_source),
        "require_real_topology": bool(args.require_real_topology),
        "require_shell_beam_mix": bool(args.require_shell_beam_mix),
        "require_case_diversity": bool(args.require_case_diversity),
        "min_topology_types": int(args.min_topology_types),
        "min_hazard_types": int(args.min_hazard_types),
        "min_material_types": int(args.min_material_types),
        "allow_sanity_sample": bool(args.allow_sanity_sample),
        "gpu_strict": bool(args.gpu_strict),
        "ci_mode": str(args.ci_mode),
        "scale_levels_pr": str(args.scale_levels_pr),
        "scale_levels_nightly": str(args.scale_levels_nightly),
        "partition_max_projection_ratio": float(args.partition_max_projection_ratio),
        "partition_edge_cut_ratio_max": float(args.partition_edge_cut_ratio_max),
        "partition_halo_node_ratio_max": float(args.partition_halo_node_ratio_max),
        "noise_seeds": str(args.noise_seeds),
        "noise_stiffness_levels_pct": str(args.noise_stiffness_levels_pct),
        "noise_stage_thresholds_pct": str(args.noise_stage_thresholds_pct),
        "noise_limit_cases": int(args.noise_limit_cases),
        "noise_target_split": str(args.noise_target_split),
        "noise_min_topology_types": int(args.noise_min_topology_types),
        "noise_min_hazard_types": int(args.noise_min_hazard_types),
        "noise_min_seed_count": int(args.noise_min_seed_count),
        "noise_stagewise_execution": bool(args.noise_stagewise_execution),
        "noise_stop_on_stage_fail": bool(args.noise_stop_on_stage_fail),
        "allow_cpu_required": bool(args.allow_cpu_required),
    }

    out = Path(args.summary_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []
    reason_code = "PASS"

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_phase3_megastructure_pipeline")
        if int(args.benchmark_top_k) > int(args.benchmark_branches):
            raise ValueError("benchmark_top_k cannot exceed benchmark_branches")
        if bool(args.gpu_strict) and not bool(args.allow_cpu_required):
            RUN_ENV_OVERRIDES["PHASE1_DISABLE_CPU_FALLBACK"] = "1"
            RUN_ENV_OVERRIDES["PHASE1_GPU_PREPROCESS"] = "1"
            RUN_ENV_OVERRIDES["PHASE1_GPU_PREPROCESS_STRICT"] = "1"

        log_event(logger, logging.INFO, "phase3.pipeline.start", candidate_id=candidate_id, ci_mode=str(args.ci_mode))

        conv_cmd = [
            sys.executable,
            "implementation/phase1/build_cases_from_megastructure_open.py",
            "--input-path",
            str(args.input_path),
            "--candidate-id",
            candidate_id,
            "--catalog",
            str(args.catalog),
            "--dynamic-out",
            str(args.dynamic_out),
            "--benchmark-out",
            str(args.benchmark_cases_out),
            "--report-out",
            str(args.conversion_report),
            "--source-manifest-out",
            str(args.source_manifest_report),
            "--case-id-prefix",
            candidate_id,
            "--require-source-manifest",
            "--min-topology-types",
            str(int(args.min_topology_types)),
            "--min-hazard-types",
            str(int(args.min_hazard_types)),
            "--min-material-types",
            str(int(args.min_material_types)),
            *( ["--download-if-missing"] if bool(args.download_if_missing) else [] ),
        ]
        # argparse.BooleanOptionalAction generated flags are --forbid-local-sanity-wave / --no-forbid-local-sanity-wave
        if bool(args.allow_sanity_sample):
            conv_cmd.append("--no-forbid-local-sanity-wave")
        else:
            conv_cmd.append("--forbid-local-sanity-wave")

        if not _run("convert_open_megastructure", conv_cmd, steps):
            reason_code = "ERR_CONVERSION_FAIL"

        conv = _load_json(str(args.conversion_report))
        src_manifest = _load_json(str(args.source_manifest_report))
        topology: dict = {}
        mgt: dict = {}
        sync: dict = {}
        topology_source = "none"
        partition_graph_source = "dynamic_jsonl"
        mgt_requested = bool(str(args.mgt_model).strip())
        mgt_pass = not mgt_requested

        real_source_verified = bool((conv.get("checks") or {}).get("source_manifest_pass", False)) and bool(src_manifest.get("source_manifest_pass", False))
        synthetic_detected = bool((conv.get("checks") or {}).get("synthetic_source_detected", False)) or bool(src_manifest.get("synthetic_source_detected", False))
        sample_source_blocked = bool((not synthetic_detected) or bool(args.allow_sanity_sample))
        case_diversity_pass = bool(
            (conv.get("checks") or {}).get("topology_diversity_pass", False)
            and (conv.get("checks") or {}).get("hazard_diversity_pass", False)
            and (conv.get("checks") or {}).get("material_diversity_pass", False)
        )

        if reason_code == "PASS" and bool(args.require_real_source) and (not real_source_verified or not sample_source_blocked):
            reason_code = "ERR_REAL_SOURCE_FAIL"
        if reason_code == "PASS" and bool(args.require_case_diversity) and not case_diversity_pass:
            reason_code = "ERR_DIVERSITY_FAIL"

        if reason_code == "PASS":
            if mgt_requested:
                mgt_cmd = [
                    sys.executable,
                    "implementation/phase1/parse_midas_mgt_to_json_npz.py",
                    "--mgt",
                    str(args.mgt_model),
                    "--json-out",
                    str(args.mgt_json_out),
                    "--npz-out",
                    str(args.mgt_npz_out),
                    "--edge-list-out",
                    str(args.mgt_edge_list_out),
                    "--report-out",
                    str(args.mgt_report_out),
                    "--forbid-synthetic-source",
                ]
                if bool(args.require_shell_beam_mix):
                    mgt_cmd.append("--require-shell-beam-mix")
                else:
                    mgt_cmd.append("--no-require-shell-beam-mix")
                if not _run("parse_midas_mgt_topology", mgt_cmd, steps):
                    reason_code = "ERR_MIDAS_MGT_FAIL"
                mgt = _load_json(str(args.mgt_report_out))
                mgt_pass = bool(mgt.get("contract_pass", False))
                if reason_code == "PASS" and not mgt_pass:
                    reason_code = "ERR_MIDAS_MGT_FAIL"

        if reason_code == "PASS":
            opensees_model = Path(str(args.opensees_model))
            if opensees_model.exists():
                topo_cmd = [
                    sys.executable,
                    "implementation/phase1/parse_opensees_to_csr.py",
                    "--model",
                    str(args.opensees_model),
                    "--edges-out",
                    str(args.topology_edges_out),
                    "--csr-out",
                    str(args.topology_csr_out),
                    "--report-out",
                    str(args.topology_report_out),
                ]
                if bool(args.require_real_topology):
                    topo_cmd.append("--require-real-topology")
                    topo_cmd.append("--forbid-synthetic-source")
                else:
                    topo_cmd.extend(["--no-require-real-topology", "--no-forbid-synthetic-source"])
                if bool(args.require_shell_beam_mix):
                    topo_cmd.append("--require-shell-beam-mix")
                else:
                    topo_cmd.append("--no-require-shell-beam-mix")
                if not _run("parse_opensees_topology", topo_cmd, steps):
                    reason_code = "ERR_TOPOLOGY_FAIL"
                topology = _load_json(str(args.topology_report_out))
                topology_source = "opensees"
            else:
                if mgt_requested and mgt_pass:
                    topology = mgt
                    topology_source = "mgt"
                else:
                    reason_code = "ERR_TOPOLOGY_FAIL"

            if reason_code == "PASS":
                if topology_source == "opensees":
                    if bool(args.require_real_topology):
                        if not bool(topology.get("contract_pass", False)) or not bool((topology.get("checks") or {}).get("real_topology_pass", False)):
                            reason_code = "ERR_TOPOLOGY_FAIL"
                elif topology_source == "mgt":
                    if not bool(topology.get("contract_pass", False)):
                        reason_code = "ERR_TOPOLOGY_FAIL"

        if reason_code == "PASS":
            bench_cmd = [
                sys.executable,
                "implementation/phase1/benchmark_kpi_contract.py",
                "--cases",
                str(args.benchmark_cases_out),
                "--out",
                str(args.benchmark_out),
                "--comparison-out",
                str(args.comparison_out),
                "--target-split",
                str(args.benchmark_target_split),
                "--epochs",
                str(args.benchmark_epochs),
                "--branches",
                str(args.benchmark_branches),
                "--top-k",
                str(args.benchmark_top_k),
                "--lr",
                str(args.benchmark_lr),
                "--epsilon",
                str(args.benchmark_epsilon),
                "--temperature",
                str(args.benchmark_temperature),
                "--seed",
                str(args.benchmark_seed),
                "--max-drift-error-pct",
                str(float(args.max_drift_error_pct)),
                "--max-base-shear-error-pct",
                str(float(args.max_base_shear_error_pct)),
                "--min-mode-shape-mac",
                str(float(args.min_mode_shape_mac)),
                "--max-buckling-factor-error-pct",
                str(float(args.max_buckling_factor_error_pct)),
                "--require-direct-metrics",
                "--accepted-metric-sources",
                "engine_export_direct,commercial_solver_export,open_data_measurement",
            ]
            if not _run("benchmark_topk_open", bench_cmd, steps):
                reason_code = "ERR_BENCHMARK_FAIL"

        if reason_code == "PASS":
            noise_cmd = [
                sys.executable,
                "implementation/phase1/run_noise_convergence_gate.py",
                "--cases",
                str(args.benchmark_cases_out),
                "--target-split",
                str(args.noise_target_split),
                "--limit-cases",
                str(int(args.noise_limit_cases)),
                "--seeds",
                str(args.noise_seeds),
                "--stiffness-noise-levels",
                str(args.noise_stiffness_levels_pct),
                "--stage-noise-thresholds",
                str(args.noise_stage_thresholds_pct),
                "--min-seed-count",
                str(int(args.noise_min_seed_count)),
                "--min-topology-types",
                str(int(args.noise_min_topology_types)),
                "--min-hazard-types",
                str(int(args.noise_min_hazard_types)),
                "--out",
                str(args.noise_convergence_out),
            ]
            if bool(args.noise_stagewise_execution):
                noise_cmd.append("--stagewise-execution")
            else:
                noise_cmd.append("--no-stagewise-execution")
            if bool(args.noise_stop_on_stage_fail):
                noise_cmd.append("--stop-on-stage-fail")
            else:
                noise_cmd.append("--no-stop-on-stage-fail")
            if not _run("noise_convergence_gate", noise_cmd, steps):
                reason_code = "ERR_NOISE_CONVERGENCE_FAIL"

        if reason_code == "PASS":
            levels = str(args.scale_levels_pr) if str(args.ci_mode) == "pr" else str(args.scale_levels_nightly)
            part_cmd = [
                sys.executable,
                "implementation/phase1/run_partitioned_scaleout.py",
                "--dof-levels",
                levels,
                "--branches",
                "64",
                "--chunk-candidates",
                "64,32,16,8,4,2,1",
                *( ["--gpu-strict"] if bool(args.gpu_strict) else [] ),
                "--max-projection-ratio",
                str(float(args.partition_max_projection_ratio)),
                "--edge-cut-ratio-max",
                str(float(args.partition_edge_cut_ratio_max)),
                "--halo-node-ratio-max",
                str(float(args.partition_halo_node_ratio_max)),
                "--ci-mode",
                str(args.ci_mode),
                "--out",
                str(args.partitioned_scaleout_out),
                *( ["--allow-cpu-required"] if bool(args.allow_cpu_required) else [] ),
            ]
            use_mgt_partition_graph = bool(
                mgt_requested
                and bool(args.prefer_mgt_for_partition)
                and Path(str(args.mgt_edge_list_out)).exists()
            )
            if use_mgt_partition_graph:
                partition_graph_source = "mgt_edge_list"
                part_cmd.extend(["--edge-list-json", str(args.mgt_edge_list_out)])
            elif Path(str(args.topology_edges_out)).exists():
                partition_graph_source = "opensees_edge_list"
                part_cmd.extend(["--edge-list-json", str(args.topology_edges_out)])
            else:
                partition_graph_source = "dynamic_jsonl"
                part_cmd.extend(["--graph-jsonl", str(args.dynamic_out)])
            if bool(args.require_real_source):
                part_cmd.append("--require-real-graph")
            if not _run("partitioned_scaleout", part_cmd, steps):
                reason_code = "ERR_PARTITION_SCALE_FAIL"

        if reason_code == "PASS":
            topology_report_for_sync = (
                str(args.topology_report_out)
                if topology_source == "opensees"
                else str(args.mgt_report_out)
            )
            sync_cmd = [
                sys.executable,
                "implementation/phase1/run_sync_stress_gate.py",
                "--partitioned-scaleout",
                str(args.partitioned_scaleout_out),
                "--topology-report",
                topology_report_for_sync,
                "--sync-backend",
                "feti_lite",
                "--require-feti-backend",
                "--require-inline-native-smoke",
                "--inline-native-ground-motion-csv",
                str(args.sync_inline_ground_motion_csv),
                "--inline-native-max-steps",
                str(int(args.sync_inline_max_steps)),
                "--ci-mode",
                str(args.ci_mode),
                "--out",
                str(args.sync_stress_out),
            ]
            if topology_source == "mgt":
                sync_cmd.append("--no-require-topology-gate")
            elif bool(args.require_real_topology):
                sync_cmd.append("--require-topology-gate")
            else:
                sync_cmd.append("--no-require-topology-gate")
            if not _run("sync_stress_gate", sync_cmd, steps):
                reason_code = "ERR_SYNC_STRESS_FAIL"

        bench = _load_json(str(args.benchmark_out))
        noise = _load_json(str(args.noise_convergence_out))
        part = _load_json(str(args.partitioned_scaleout_out))
        if not topology:
            if topology_source == "mgt":
                topology = _load_json(str(args.mgt_report_out))
            else:
                topology = _load_json(str(args.topology_report_out))
        if not mgt and mgt_requested:
            mgt = _load_json(str(args.mgt_report_out))
        sync = _load_json(str(args.sync_stress_out))

        pr_scale_pass = bool((part.get("checks") or {}).get("pr_scale_pass", False))
        nightly_scale_pass = bool((part.get("checks") or {}).get("nightly_scale_pass", False))
        gpu_strict_pass = bool((part.get("checks") or {}).get("gpu_strict_pass", not bool(args.gpu_strict)))
        projection_ratio_pass = bool((part.get("checks") or {}).get("projection_ratio_pass", False))
        graph_source_is_real = bool((part.get("checks") or {}).get("graph_source_is_real", False))
        partition_quality_threshold_pass = bool((part.get("checks") or {}).get("partition_quality_threshold_pass", False))

        topology_gate_pass = False
        if topology_source == "mgt":
            topology_gate_pass = bool(topology.get("contract_pass", False)) and bool(
                (topology.get("checks") or {}).get("synthetic_source_blocked", False)
            )
        else:
            topology_gate_pass = bool(topology.get("contract_pass", False)) and bool(
                (topology.get("checks") or {}).get("real_topology_pass", False)
            )
        shell_beam_mix_pass = bool((topology.get("checks") or {}).get("shell_beam_mix_pass", False))

        checks = {
            "real_source_verified": bool(real_source_verified),
            "sample_source_blocked": bool(sample_source_blocked),
            "case_diversity_pass": bool(case_diversity_pass),
            "mgt_conversion_pass": bool(mgt_pass),
            "topology_gate_pass": bool(topology_gate_pass),
            "shell_beam_mix_pass": bool(shell_beam_mix_pass),
            "topology_source_is_mgt": bool(topology_source == "mgt"),
            "partition_graph_uses_mgt": bool(partition_graph_source == "mgt_edge_list"),
            "benchmark_pass": bool(bench.get("contract_pass", False)),
            "noise_convergence_pass": bool(noise.get("contract_pass", False)),
            "noise_seed_diversity_pass": bool((noise.get("checks") or {}).get("has_seed_diversity", False)),
            "noise_case_diversity_pass": bool((noise.get("checks") or {}).get("case_diversity_pass", False)),
            "noise_stagewise_pass": bool((noise.get("checks") or {}).get("stagewise_execution_pass", False)),
            "gpu_strict_pass": bool(gpu_strict_pass),
            "pr_scale_pass": bool(pr_scale_pass),
            "nightly_scale_pass": bool(nightly_scale_pass),
            "projection_ratio_pass": bool(projection_ratio_pass),
            "graph_source_is_real": bool(graph_source_is_real),
            "partition_quality_threshold_pass": bool(partition_quality_threshold_pass),
            "sync_stress_pass": bool(sync.get("contract_pass", False)),
            "sync_backend_policy_pass": bool((sync.get("checks") or {}).get("backend_policy_pass", False)),
            "sync_virtual_blocked_pass": bool((sync.get("checks") or {}).get("virtual_sync_blocked_pass", False)),
            "sync_feti_profile_pass": bool((sync.get("checks") or {}).get("feti_profile_pass", False)),
            "sync_inline_native_smoke_pass": bool((sync.get("checks") or {}).get("inline_native_smoke_pass", False)),
        }

        if reason_code == "PASS" and bool(args.gpu_strict) and not gpu_strict_pass:
            reason_code = "ERR_GPU_STRICT_FAIL"
        if reason_code == "PASS" and mgt_requested and not checks["mgt_conversion_pass"]:
            reason_code = "ERR_MIDAS_MGT_FAIL"
        if reason_code == "PASS" and not checks["sync_backend_policy_pass"]:
            reason_code = "ERR_SYNC_STRESS_FAIL"
        if reason_code == "PASS" and not checks["sync_virtual_blocked_pass"]:
            reason_code = "ERR_SYNC_STRESS_FAIL"
        if reason_code == "PASS" and not checks["sync_feti_profile_pass"]:
            reason_code = "ERR_SYNC_STRESS_FAIL"
        if reason_code == "PASS" and not checks["sync_inline_native_smoke_pass"]:
            reason_code = "ERR_SYNC_STRESS_FAIL"
        if reason_code == "PASS" and str(args.ci_mode) == "nightly" and not nightly_scale_pass:
            reason_code = "ERR_NIGHTLY_10M_FAIL"

        contract_pass = bool(
            reason_code == "PASS"
            and checks["real_source_verified"]
            and checks["sample_source_blocked"]
            and (checks["mgt_conversion_pass"] if mgt_requested else True)
            and (checks["case_diversity_pass"] if bool(args.require_case_diversity) else True)
            and (checks["topology_gate_pass"] if bool(args.require_real_topology) else True)
            and (checks["shell_beam_mix_pass"] if bool(args.require_shell_beam_mix) else True)
            and checks["benchmark_pass"]
            and checks["noise_convergence_pass"]
            and checks["noise_seed_diversity_pass"]
            and checks["noise_case_diversity_pass"]
            and checks["noise_stagewise_pass"]
            and checks["sync_stress_pass"]
            and checks["sync_virtual_blocked_pass"]
            and checks["sync_feti_profile_pass"]
            and checks["sync_inline_native_smoke_pass"]
            and checks["gpu_strict_pass"]
            and checks["projection_ratio_pass"]
            and checks["graph_source_is_real"]
            and checks["partition_quality_threshold_pass"]
            and (checks["pr_scale_pass"] if str(args.ci_mode) == "pr" else checks["nightly_scale_pass"])
        )
        if reason_code == "PASS" and not contract_pass:
            reason_code = "ERR_SUMMARY_FAIL"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-megastructure-open-pipeline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "recommended_candidates": {
                "primary": primary,
                "secondary": secondary,
            },
            "reports": {
                "conversion": str(args.conversion_report),
                "source_manifest": str(args.source_manifest_report),
                "topology": str(args.topology_report_out) if topology_source == "opensees" else str(args.mgt_report_out),
                "mgt_conversion": str(args.mgt_report_out),
                "mgt_edge_list": str(args.mgt_edge_list_out),
                "benchmark": str(args.benchmark_out),
                "comparison": str(args.comparison_out),
                "noise_convergence": str(args.noise_convergence_out),
                "partitioned_scaleout": str(args.partitioned_scaleout_out),
                "sync_stress": str(args.sync_stress_out),
            },
            "topology_source": topology_source,
            "partition_graph_source": partition_graph_source,
            "checks": checks,
            "steps": steps,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name=f"phase3_pipeline_{str(args.ci_mode)}",
            paths=[
                str(args.summary_out),
                str(args.conversion_report),
                str(args.source_manifest_report),
                str(args.dynamic_out),
                str(args.topology_report_out),
                str(args.topology_edges_out),
                str(args.topology_csr_out),
                str(args.mgt_report_out),
                str(args.mgt_json_out),
                str(args.mgt_npz_out),
                str(args.mgt_edge_list_out),
                str(args.benchmark_cases_out),
                str(args.benchmark_out),
                str(args.comparison_out),
                str(args.noise_convergence_out),
                str(args.partitioned_scaleout_out),
                str(args.sync_stress_out),
            ],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        log_event(logger, logging.INFO, "phase3.pipeline.completed", contract_pass=bool(contract_pass), reason_code=reason_code)
        print(f"Wrote phase3 megastructure pipeline report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-megastructure-open-pipeline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "steps": steps,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive_outputs(
            test_name=f"phase3_pipeline_{str(args.ci_mode)}",
            paths=[str(args.summary_out), str(args.conversion_report), str(args.source_manifest_report), str(args.dynamic_out)],
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote phase3 megastructure pipeline report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
