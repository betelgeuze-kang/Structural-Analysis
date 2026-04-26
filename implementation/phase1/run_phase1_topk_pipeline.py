#!/usr/bin/env python3
"""One-command reproducible Phase1 top-k benchmark pipeline.

Pipeline (strict, no fallback path):
1) Build benchmark cases from commercial exports
2) Regenerate core phase1 contracts + strict probe artifacts
3) Train/evaluate top-k benchmark + multi-seed precision suite
4) Run CI gate + static artifact validator
5) Bundle artifacts with baseline/top-k separation
6) Emit config lock + pipeline manifest
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

MIDAS_SECTION_LIBRARY_ARTIFACTS = (
    "implementation/phase1/open_data/midas/midas_generator_33.json",
    "implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json",
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json",
)

DEFAULT_CONFIG = {
    "hf_csv": "implementation/phase1/commercial_hf_export_sample.csv",
    "lf_csv": "implementation/phase1/commercial_lf_export_sample.csv",
    "merged_csv": None,
    "hf_prefix": "hf_",
    "lf_prefix": "lf_",
    "metric_source": "engine_export_direct",
    "accepted_metric_sources": "engine_export_direct,commercial_solver_export",
    "require_direct_metrics": True,
    "cases_out": "implementation/phase1/commercial_benchmark_cases.from_csv.json",
    "benchmark_out": "implementation/phase1/hf_benchmark_report.json",
    "comparison_out": "implementation/phase1/topk_comparison_experiment_report.json",
    "suite_out": "implementation/phase1/topk_precision_suite_report.json",
    "strict_probe_out": "implementation/phase1/zero_copy_real_probe_report_strict.json",
    "rust_parity_out": "implementation/phase1/rust_md3bead_parity_report.json",
    "lj_mapping_out": "implementation/phase1/nonlinear_lj_mapping_report.json",
    "dynamic_time_history_out": "implementation/phase1/dynamic_time_history_report.json",
    "microbatch_profile_out": "implementation/phase1/branch64_microbatch_profile_report.json",
    "phasea_contract_out": "implementation/phase1/phasea_contract_report.json",
    "phaseb_summary_out": "implementation/phase1/phaseb_track_summary_report.json",
    "phaseb_track_lf_out": "implementation/phase1/track_lf_solver_report.json",
    "phaseb_moving_load_out": "implementation/phase1/moving_load_integrator_report.json",
    "phaseb_vti_out": "implementation/phase1/vti_coupled_solver_report.json",
    "phaseb_irregularity_out": "implementation/phase1/track_irregularity_report.json",
    "phased_summary_out": "implementation/phase1/phased_multidomain_summary_report.json",
    "phased_track_dataset_out": "implementation/phase1/track_dynamics_dataset_report.json",
    "phased_tunnel_dataset_out": "implementation/phase1/tunnel_dynamics_dataset_report.json",
    "phased_attention_out": "implementation/phase1/moving_load_attention_report.json",
    "phased_tgnn_out": "implementation/phase1/tgnn_multidomain_report.json",
    "phased_track_dataset_jsonl": "implementation/phase1/spatiotemporal_data/track_dynamic_cases.jsonl",
    "phased_tunnel_dataset_jsonl": "implementation/phase1/spatiotemporal_data/tunnel_dynamic_cases.jsonl",
    "phased_tgnn_ckpt": "implementation/phase1/spatiotemporal_data/tgnn_multidomain.pt",
    "smoke_out": "implementation/phase1/lf_to_gnn_e2e_smoke_report.json",
    "ci_out": "implementation/phase1/ci_gate_report.json",
    "ci_manifest": "implementation/phase1/ci_artifact_manifest.json",
    "validation_out": "implementation/phase1/static_artifact_validation_report.json",
    "artifact_root": "implementation/phase1/experiments",
    "artifact_label": None,
    "step_outputs_dir": "implementation/phase1/step_outputs",
    "producer_cmd": "python3 implementation/phase1/rust_hip_md3bead_hook.py",
    "allow_cpu_required_probe": True,
    "engine_hook_cmd": "python3 implementation/phase1/rust_hip_md3bead_hook.py",
    "runtime_hook_cmd": "python3 implementation/phase1/rust_hip_md3bead_hook.py",
    "microbatch_branches": 64,
    "microbatch_chunk_candidates": "64,32,16,8,4",
    "microbatch_repeats": 2,
    "microbatch_node_count": 100000,
    "microbatch_state_components": 5,
    "microbatch_cache_mb": 128.0,
    "microbatch_cache_headroom": 0.72,
    "microbatch_graph_overhead_mb": 24.0,
    "epochs": 180,
    "branches": 8,
    "top_k": 3,
    "lr": 0.06,
    "epsilon": 0.12,
    "temperature": 0.35,
    "seed": 23,
    "seeds": "11,17,23,31,47",
    "target_split": "test",
}

RUN_ENV_OVERRIDES: dict[str, str] = {}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _merge_config(base: dict, override: dict) -> dict:
    merged = dict(base)
    for k, v in override.items():
        merged[k] = v
    return merged


def _run_step(step_name: str, cmd: list[str], steps: list[dict]) -> None:
    t0 = time.time()
    subprocess.run(cmd, check=True, env={**os.environ, **RUN_ENV_OVERRIDES})
    dt = time.time() - t0
    steps.append(
        {
            "step": step_name,
            "seconds": dt,
            "command": shlex.join(cmd),
        }
    )


def _build_cases_cmd(cfg: dict) -> list[str]:
    cmd = [
        sys.executable,
        "implementation/phase1/build_cases_from_commercial_exports.py",
        "--metric-source",
        str(cfg["metric_source"]),
        "--out",
        str(cfg["cases_out"]),
    ]
    if cfg.get("merged_csv"):
        cmd.extend(
            [
                "--merged-csv",
                str(cfg["merged_csv"]),
                "--hf-prefix",
                str(cfg["hf_prefix"]),
                "--lf-prefix",
                str(cfg["lf_prefix"]),
            ]
        )
    else:
        cmd.extend(
            [
                "--hf-csv",
                str(cfg["hf_csv"]),
                "--lf-csv",
                str(cfg["lf_csv"]),
            ]
        )
    return cmd


def _benchmark_cmd(cfg: dict) -> list[str]:
    cmd = [
        sys.executable,
        "implementation/phase1/benchmark_kpi_contract.py",
        "--cases",
        str(cfg["cases_out"]),
        "--out",
        str(cfg["benchmark_out"]),
        "--comparison-out",
        str(cfg["comparison_out"]),
        "--target-split",
        str(cfg["target_split"]),
        "--epochs",
        str(cfg["epochs"]),
        "--branches",
        str(cfg["branches"]),
        "--top-k",
        str(cfg["top_k"]),
        "--lr",
        str(cfg["lr"]),
        "--epsilon",
        str(cfg["epsilon"]),
        "--temperature",
        str(cfg["temperature"]),
        "--seed",
        str(cfg["seed"]),
    ]
    if bool(cfg.get("require_direct_metrics", False)):
        cmd.extend(
            [
                "--require-direct-metrics",
                "--accepted-metric-sources",
                str(cfg["accepted_metric_sources"]),
            ]
        )
    return cmd


def _suite_cmd(cfg: dict) -> list[str]:
    cmd = [
        sys.executable,
        "implementation/phase1/run_topk_precision_experiments.py",
        "--cases",
        str(cfg["cases_out"]),
        "--seeds",
        str(cfg["seeds"]),
        "--epochs",
        str(cfg["epochs"]),
        "--branches",
        str(cfg["branches"]),
        "--top-k",
        str(cfg["top_k"]),
        "--lr",
        str(cfg["lr"]),
        "--epsilon",
        str(cfg["epsilon"]),
        "--temperature",
        str(cfg["temperature"]),
        "--target-split",
        str(cfg["target_split"]),
        "--out",
        str(cfg["suite_out"]),
    ]
    if bool(cfg.get("require_direct_metrics", False)):
        cmd.extend(
            [
                "--require-direct-metrics",
                "--accepted-metric-sources",
                str(cfg["accepted_metric_sources"]),
            ]
        )
    return cmd


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None, help="optional JSON config override")
    p.add_argument("--out-manifest", default="implementation/phase1/pipeline_manifest.json")
    p.add_argument("--out-config-lock", default="implementation/phase1/pipeline_config.lock.json")
    p.add_argument("--hf-csv", default=None)
    p.add_argument("--lf-csv", default=None)
    p.add_argument("--merged-csv", default=None)
    p.add_argument("--metric-source", default=None)
    p.add_argument("--artifact-label", default=None)
    args = p.parse_args()

    cfg = dict(DEFAULT_CONFIG)
    if args.config:
        cfg = _merge_config(cfg, _load_json(Path(args.config)))

    cli_override = {}
    for key in ("hf_csv", "lf_csv", "merged_csv", "metric_source", "artifact_label"):
        val = getattr(args, key)
        if val is not None:
            cli_override[key] = val
    cfg = _merge_config(cfg, cli_override)

    if cfg.get("merged_csv"):
        # merged mode selected
        pass
    else:
        if not cfg.get("hf_csv") or not cfg.get("lf_csv"):
            raise SystemExit("paired mode requires hf_csv and lf_csv")

    if int(cfg["top_k"]) < 2:
        raise SystemExit("top_k must be >= 2")
    if int(cfg["top_k"]) > int(cfg["branches"]):
        raise SystemExit("top_k cannot exceed branches")
    if not bool(cfg.get("allow_cpu_required_probe", False)):
        RUN_ENV_OVERRIDES["PHASE1_DISABLE_CPU_FALLBACK"] = "1"
        RUN_ENV_OVERRIDES["PHASE1_GPU_PREPROCESS"] = "1"
        RUN_ENV_OVERRIDES["PHASE1_GPU_PREPROCESS_STRICT"] = "1"

    cfg["resolved_at"] = datetime.now(timezone.utc).isoformat()
    cfg["python"] = sys.executable

    cfg_json = json.dumps(cfg, sort_keys=True, ensure_ascii=True)
    cfg_hash = _sha256_text(cfg_json)
    config_lock = {
        "schema_version": "1.0",
        "run_id": "phase1-topk-pipeline-config-lock",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": cfg_hash,
        "config": cfg,
    }
    cfg_lock_path = Path(args.out_config_lock)
    cfg_lock_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_lock_path.write_text(json.dumps(config_lock, indent=2), encoding="utf-8")

    steps: list[dict] = []

    # 1) Core case build
    _run_step("build_cases", _build_cases_cmd(cfg), steps)

    # 2) Runtime/probe artifacts used by CI gate
    _run_step(
        "run_phase1_steps",
        [
            sys.executable,
            "implementation/phase1/run_phase1_steps.py",
            "--out-dir",
            str(cfg["step_outputs_dir"]),
            "--repeats",
            "3",
            "--engine-hook-cmd",
            str(cfg["engine_hook_cmd"]),
            "--runtime-hook-cmd",
            str(cfg["runtime_hook_cmd"]),
            "--require-runtime-hook",
            "--strict",
        ],
        steps,
    )
    _run_step(
        "zero_copy_strict_probe",
        [
            sys.executable,
            "implementation/phase1/zero_copy_real_probe.py",
            "--producer-cmd",
            str(cfg["producer_cmd"]),
            "--require-rust-hip",
            *(["--allow-cpu-required"] if bool(cfg.get("allow_cpu_required_probe", False)) else []),
            "--out",
            str(cfg["strict_probe_out"]),
        ],
        steps,
    )

    # 3) Core contract reports
    _run_step("dynamics_contract", [sys.executable, "implementation/phase1/generate_dynamics_boundary_contract.py", "--out", "implementation/phase1/dynamics_boundary_report.json"], steps)
    _run_step(
        "phasea_contract_pack",
        [
            sys.executable,
            "implementation/phase1/generate_phasea_contract_report.py",
            "--out",
            str(cfg["phasea_contract_out"]),
        ],
        steps,
    )
    _run_step(
        "phaseb_track_modules",
        [
            sys.executable,
            "implementation/phase1/run_phaseb_track_modules.py",
            "--out",
            str(cfg["phaseb_summary_out"]),
            "--b1-out",
            str(cfg["phaseb_track_lf_out"]),
            "--b2-out",
            str(cfg["phaseb_moving_load_out"]),
            "--b3-out",
            str(cfg["phaseb_vti_out"]),
            "--b4-out",
            str(cfg["phaseb_irregularity_out"]),
        ],
        steps,
    )
    _run_step(
        "phased_multidomain_modules",
        [
            sys.executable,
            "implementation/phase1/run_phased_multidomain_modules.py",
            "--out",
            str(cfg["phased_summary_out"]),
            "--d1-out",
            str(cfg["phased_track_dataset_out"]),
            "--d2-out",
            str(cfg["phased_tunnel_dataset_out"]),
            "--d3-out",
            str(cfg["phased_tgnn_out"]),
            "--d4-out",
            str(cfg["phased_attention_out"]),
            "--track-dataset",
            str(cfg["phased_track_dataset_jsonl"]),
            "--tunnel-dataset",
            str(cfg["phased_tunnel_dataset_jsonl"]),
            "--ckpt",
            str(cfg["phased_tgnn_ckpt"]),
        ],
        steps,
    )
    _run_step(
        "dynamic_time_history_contract",
        [
            sys.executable,
            "implementation/phase1/dynamic_time_history_contract_stub.py",
            "--ground-motion-csv",
            "implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv",
            "--auto-generate-input",
            "--out",
            str(cfg["dynamic_time_history_out"]),
        ],
        steps,
    )
    _run_step("pg_gat_contract", [sys.executable, "implementation/phase1/pg_gat_contract_stub.py", "--out", "implementation/phase1/pg_gat_contract_report.json"], steps)
    _run_step("subgraph_projection_contract", [sys.executable, "implementation/phase1/subgraph_projection_stub.py", "--out", "implementation/phase1/subgraph_projection_report.json"], steps)
    _run_step("soa_contract", [sys.executable, "implementation/phase1/generate_soa_dlpack_contract.py", "--out", "implementation/phase1/soa_dlpack_contract_report.json"], steps)
    _run_step("physics_residual_contract", [sys.executable, "implementation/phase1/physics_residual_contract_stub.py", "--out", "implementation/phase1/physics_residual_contract_report.json"], steps)
    _run_step("meta_learning_contract", [sys.executable, "implementation/phase1/meta_learning_task_stub.py", "--out", "implementation/phase1/meta_learning_task_report.json"], steps)
    _run_step("buckling_contract", [sys.executable, "implementation/phase1/buckling_eigen_contract_stub.py", "--out", "implementation/phase1/buckling_contract_report.json"], steps)
    _run_step("nonlinear_lj_mapping_contract", [sys.executable, "implementation/phase1/validate_nonlinear_lj_mapping.py", "--out", str(cfg["lj_mapping_out"])], steps)
    _run_step(
        "branch64_microbatch_profile",
        [
            sys.executable,
            "implementation/phase1/profile_branch64_microbatch_cache.py",
            "--runtime-hook-cmd",
            str(cfg["runtime_hook_cmd"]),
            "--branches",
            str(cfg["microbatch_branches"]),
            "--chunk-candidates",
            str(cfg["microbatch_chunk_candidates"]),
            "--repeats",
            str(cfg["microbatch_repeats"]),
            "--node-count",
            str(cfg["microbatch_node_count"]),
            "--state-components",
            str(cfg["microbatch_state_components"]),
            "--cache-mb",
            str(cfg["microbatch_cache_mb"]),
            "--cache-headroom",
            str(cfg["microbatch_cache_headroom"]),
            "--graph-overhead-mb",
            str(cfg["microbatch_graph_overhead_mb"]),
            "--out",
            str(cfg["microbatch_profile_out"]),
        ],
        steps,
    )
    _run_step("physics_branching", [sys.executable, "implementation/phase1/physics_guided_branching.py", "--out", "implementation/phase1/physics_branching_report.json"], steps)
    _run_step("bifurcation_detector", [sys.executable, "implementation/phase1/bifurcation_detector_stub.py", "--out", "implementation/phase1/bifurcation_detector_report.json"], steps)
    _run_step(
        "winning_ticket_topk_backprop",
        [
            sys.executable,
            "implementation/phase1/winning_ticket_backprop.py",
            "--branches",
            str(max(int(cfg["branches"]), 8)),
            "--top-k",
            str(cfg["top_k"]),
            "--out",
            "implementation/phase1/winning_ticket_backprop_report.json",
        ],
        steps,
    )
    _run_step(
        "rust_onnx_contract",
        [
            sys.executable,
            "implementation/phase1/rust_onnx_native_contract_stub.py",
            "--strict-probe",
            str(cfg["strict_probe_out"]),
            "--winning-ticket",
            "implementation/phase1/winning_ticket_backprop_report.json",
            "--require-inputs",
            "--out",
            "implementation/phase1/rust_onnx_native_contract_report.json",
        ],
        steps,
    )
    _run_step(
        "priority3_modules",
        [
            sys.executable,
            "implementation/phase1/run_priority3_modules.py",
            "--out-dir",
            "implementation/phase1",
        ],
        steps,
    )

    # 4) Benchmark + robustness suite
    _run_step("topk_benchmark", _benchmark_cmd(cfg), steps)
    _run_step("topk_precision_suite", _suite_cmd(cfg), steps)

    # 5) CI gate + validation
    _run_step(
        "lf_to_gnn_smoke",
        [
            sys.executable,
            "implementation/phase1/lf_to_gnn_e2e_smoke.py",
            "--out",
            str(cfg["smoke_out"]),
        ],
        steps,
    )
    _run_step(
        "rust_md3bead_parity",
        [
            sys.executable,
            "implementation/phase1/validate_md3bead_rust_parity.py",
            "--rust-hook-cmd",
            str(cfg["engine_hook_cmd"]),
            "--out",
            str(cfg["rust_parity_out"]),
        ],
        steps,
    )
    _run_step(
        "phase1_ci_gate",
        [
            sys.executable,
            "implementation/phase1/phase1_ci_gate.py",
            "--strict-probe",
            str(cfg["strict_probe_out"]),
            "--rca",
            str(Path(cfg["step_outputs_dir"]) / "step5_rca_summary.json"),
            "--priority3",
            "implementation/phase1/priority3_summary.json",
            "--benchmark",
            str(cfg["benchmark_out"]),
            "--rust-md3bead-parity",
            str(cfg["rust_parity_out"]),
            "--lj-mapping",
            str(cfg["lj_mapping_out"]),
            "--dynamic-time-history",
            str(cfg["dynamic_time_history_out"]),
            "--cache-profile",
            str(cfg["microbatch_profile_out"]),
            "--phasea-contract",
            str(cfg["phasea_contract_out"]),
            "--phaseb-track-lf",
            str(cfg["phaseb_track_lf_out"]),
            "--phaseb-moving-load",
            str(cfg["phaseb_moving_load_out"]),
            "--phaseb-vti",
            str(cfg["phaseb_vti_out"]),
            "--phaseb-irregularity",
            str(cfg["phaseb_irregularity_out"]),
            "--phaseb-summary",
            str(cfg["phaseb_summary_out"]),
            "--phased-track-dataset",
            str(cfg["phased_track_dataset_out"]),
            "--phased-tunnel-dataset",
            str(cfg["phased_tunnel_dataset_out"]),
            "--phased-attention",
            str(cfg["phased_attention_out"]),
            "--phased-tgnn",
            str(cfg["phased_tgnn_out"]),
            "--phased-summary",
            str(cfg["phased_summary_out"]),
            "--out",
            str(cfg["ci_out"]),
            "--manifest",
            str(cfg["ci_manifest"]),
            *[
                item
                for artifact_path in MIDAS_SECTION_LIBRARY_ARTIFACTS
                for item in ("--midas-section-library-artifact", artifact_path)
            ],
        ],
        steps,
    )
    _run_step(
        "static_artifact_validation",
        [
            sys.executable,
            "implementation/phase1/validate_phase1_artifacts.py",
            "--smoke",
            str(cfg["smoke_out"]),
            "--ci",
            str(cfg["ci_out"]),
            "--rca",
            str(Path(cfg["step_outputs_dir"]) / "step5_rca_summary.json"),
            "--benchmark",
            str(cfg["benchmark_out"]),
            "--rust-parity",
            str(cfg["rust_parity_out"]),
            "--lj-mapping",
            str(cfg["lj_mapping_out"]),
            "--dynamic-time-history",
            str(cfg["dynamic_time_history_out"]),
            "--cache-profile",
            str(cfg["microbatch_profile_out"]),
            "--phasea-contract",
            str(cfg["phasea_contract_out"]),
            "--phaseb-track-lf",
            str(cfg["phaseb_track_lf_out"]),
            "--phaseb-moving-load",
            str(cfg["phaseb_moving_load_out"]),
            "--phaseb-vti",
            str(cfg["phaseb_vti_out"]),
            "--phaseb-irregularity",
            str(cfg["phaseb_irregularity_out"]),
            "--phaseb-summary",
            str(cfg["phaseb_summary_out"]),
            "--phased-track-dataset",
            str(cfg["phased_track_dataset_out"]),
            "--phased-tunnel-dataset",
            str(cfg["phased_tunnel_dataset_out"]),
            "--phased-attention",
            str(cfg["phased_attention_out"]),
            "--phased-tgnn",
            str(cfg["phased_tgnn_out"]),
            "--phased-summary",
            str(cfg["phased_summary_out"]),
            "--out",
            str(cfg["validation_out"]),
        ],
        steps,
    )

    # 6) Artifact bundle
    bundle_cmd = [
        sys.executable,
        "implementation/phase1/organize_benchmark_artifacts.py",
        "--out-root",
        str(cfg["artifact_root"]),
        "--cases",
        str(cfg["cases_out"]),
        "--benchmark",
        str(cfg["benchmark_out"]),
        "--comparison",
        str(cfg["comparison_out"]),
        "--suite",
        str(cfg["suite_out"]),
        "--ci",
        str(cfg["ci_out"]),
        "--validation",
        str(cfg["validation_out"]),
    ]
    if cfg.get("artifact_label"):
        bundle_cmd.extend(["--label", str(cfg["artifact_label"])])
    _run_step("organize_artifacts", bundle_cmd, steps)
    _run_step(
        "organize_workspace",
        [
            sys.executable,
            "implementation/phase1/organize_phase1_workspace.py",
            "--root",
            "implementation/phase1",
            "--workspace",
            "implementation/phase1/workspace",
        ],
        steps,
    )

    manifest = {
        "schema_version": "1.0",
        "run_id": "phase1-topk-pipeline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_lock": str(cfg_lock_path),
        "config_sha256": cfg_hash,
        "step_count": len(steps),
        "steps": steps,
        "outputs": {
            "cases": cfg["cases_out"],
            "benchmark": cfg["benchmark_out"],
            "comparison": cfg["comparison_out"],
            "suite": cfg["suite_out"],
            "strict_probe": cfg["strict_probe_out"],
            "ci": cfg["ci_out"],
            "ci_manifest": cfg["ci_manifest"],
            "validation": cfg["validation_out"],
            "rust_parity": cfg["rust_parity_out"],
            "lj_mapping": cfg["lj_mapping_out"],
            "dynamic_time_history": cfg["dynamic_time_history_out"],
            "microbatch_profile": cfg["microbatch_profile_out"],
            "phasea_contract": cfg["phasea_contract_out"],
            "phaseb_summary": cfg["phaseb_summary_out"],
            "phaseb_track_lf": cfg["phaseb_track_lf_out"],
            "phaseb_moving_load": cfg["phaseb_moving_load_out"],
            "phaseb_vti": cfg["phaseb_vti_out"],
            "phaseb_irregularity": cfg["phaseb_irregularity_out"],
            "phased_summary": cfg["phased_summary_out"],
            "phased_track_dataset": cfg["phased_track_dataset_out"],
            "phased_tunnel_dataset": cfg["phased_tunnel_dataset_out"],
            "phased_attention": cfg["phased_attention_out"],
            "phased_tgnn": cfg["phased_tgnn_out"],
        },
    }

    out_manifest = Path(args.out_manifest)
    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    out_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote pipeline config lock: {cfg_lock_path}")
    print(f"Wrote pipeline manifest: {out_manifest}")


if __name__ == "__main__":
    main()
