#!/usr/bin/env python3
"""Static validator for mobile-web Phase1 artifacts.

Validates report contracts without HIP/Torch runtime dependencies.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


ALLOWED_SMOKE_REASON = {
    "PASS",
    "ERR_EMPTY_NODES",
    "ERR_EMPTY_EDGES",
    "ERR_META_UNIT",
    "ERR_EMPTY_CORRECTION",
    "ERR_RESIDUAL_ACCURACY",
    "ERR_COMPLEXITY_GUARDRAIL",
}

ALLOWED_CI_REASON = {
    "PASS",
    "ERR_MISSING_STRICT_KEY",
    "ERR_MISSING_RCA_KEY",
    "ERR_INVALID_RCA_VALUE",
    "ERR_STRICT_FAIL",
    "ERR_HOST_COPY_SHARE",
    "ERR_MISSING_CONTRACT_ARTIFACT",
    "ERR_PRIORITY3_FAIL",
    "ERR_BUCKLING_EIGEN_INVALID",
    "ERR_ENERGY_MONOTONICITY",
    "ERR_META_OOD_FAIL",
    "ERR_BENCHMARK_KPI_FAIL",
    "ERR_BRANCHING_CONTRACT_FAIL",
    "ERR_BIFURCATION_CONTRACT_FAIL",
    "ERR_RUST_ONNX_CONTRACT_FAIL",
    "ERR_WINNING_TICKET_FAIL",
    "ERR_RUST_MD3BEAD_PARITY_FAIL",
    "ERR_LJ_MAPPING_FAIL",
    "ERR_DYNAMIC_TIME_HISTORY_FAIL",
    "ERR_CACHE_PROFILE_FAIL",
    "ERR_P0_ENGINE_PROFILE_FAIL",
    "ERR_HIP_KERNEL_SMOKE_FAIL",
    "ERR_P0_HIP_KERNEL_FAIL",
    "ERR_P0_CORE_GAP_FAIL",
    "ERR_NOISE_STRESS_FAIL",
    "ERR_SCALEOUT_IO_FAIL",
    "ERR_REAL_SOURCE_FAIL",
    "ERR_TOPOLOGY_GATE_FAIL",
    "ERR_SYNC_STRESS_FAIL",
    "ERR_GPU_STRICT_FAIL",
    "ERR_PARTITION_SCALE_FAIL",
    "ERR_NOISE_CONVERGENCE_FAIL",
    "ERR_NIGHTLY_10M_FAIL",
    "ERR_NIGHTLY_10M_REPRO_FAIL",
    "ERR_NDTHA_LONG_PROFILE_FAIL",
    "ERR_COMMERCIAL_CSV_GATE_FAIL",
    "ERR_MIDAS_MGT_CONVERSION_FAIL",
    "ERR_PHASEA_CONTRACT_FAIL",
    "ERR_PHASEB_TRACK_FAIL",
    "ERR_PHASED_ML_FAIL",
    "ERR_PHASEE_INTEGRATED_FAIL",
    "ERR_PHASEF_RESILIENCE_FAIL",
    "ERR_COMMERCIAL_READINESS_FAIL",
    "ERR_REAL_SOURCE_MULTI_FAIL",
    "ERR_NONLINEAR_ENGINE_FAIL",
    "ERR_PUSHOVER_STRESS_FAIL",
    "ERR_NDTHA_STRESS_FAIL",
    "ERR_NDTHA_RESIDUAL_FAIL",
    "ERR_PBD_REVIEW_FAIL",
    "ERR_GLOBAL_AUTHORITY_FAIL",
    "ERR_WIND_BENCHMARK_FAIL",
    "ERR_SSI_BOUNDARY_FAIL",
    "ERR_DAMPER_VALIDATION_FAIL",
    "ERR_KDS_FRONTEND_FAIL",
    "ERR_CONSTRUCTION_SEQUENCE_FAIL",
    "ERR_FLEXIBLE_DIAPHRAGM_FAIL",
    "ERR_REPRO_VERSION_LOCK_FAIL",
    "ERR_SOLVER_HIP_E2E_FAIL",
    "ERR_RC_BENCHMARK_LOCK_FAIL",
    "ERR_RELEASE_REGISTRY_FAIL",
}

ALLOWED_PRIORITY_REASON = {
    "PASS",
    "ERR_MODULE_FAIL",
    "ERR_METADATA_VERSION_MISMATCH",
}

ALLOWED_DYN_REASON = {
    "PASS",
    "ERR_NODE_FIELD_MISSING",
    "ERR_SUPPORT_TYPE_INVALID",
    "ERR_DAMPING_INVALID",
    "ERR_DT_INVALID",
}

ALLOWED_PHYSICS_RESIDUAL_REASON = {
    "PASS",
    "ERR_EQ_RESIDUAL",
    "ERR_BOUNDARY_VIOLATION",
    "ERR_DAMPING_RANGE",
    "ERR_ENERGY_MONOTONICITY",
}

ALLOWED_META_LEARNING_REASON = {
    "PASS",
    "ERR_TASK_SCHEMA",
}

ALLOWED_BUCKLING_REASON = {
    "PASS",
    "ERR_BUCKLING_EIGEN_INVALID",
}

ALLOWED_BENCHMARK_REASON = {
    "PASS",
    "ERR_BENCHMARK_KPI_FAIL",
}

ALLOWED_BRANCHING_REASON = {
    "PASS",
    "ERR_EMPTY_BASIS",
}

ALLOWED_BIFURCATION_REASON = {
    "PASS",
    "WARN_NO_BIFURCATION_EVENT",
}

ALLOWED_RUST_ONNX_REASON = {
    "PASS",
    "ERR_RUST_ONNX_CONTRACT",
}

ALLOWED_WINNING_TICKET_REASON = {
    "PASS",
    "ERR_TARGETED_BACKPROP",
    "ERR_EMPTY_BASIS",
    "ERR_TOPK_INVALID",
    "ERR_TORCH_UNAVAILABLE",
}

ALLOWED_RUST_PARITY_REASON = {
    "PASS",
    "ERR_HOOK_EXEC",
    "ERR_PARITY_STEP1",
    "ERR_PARITY_STEP5",
}

ALLOWED_LJ_MAPPING_REASON = {
    "PASS",
    "ERR_LJ_YIELD",
    "ERR_LJ_SOFTENING",
    "ERR_LJ_DISSIPATION",
}

ALLOWED_DYNAMIC_TIME_HISTORY_REASON = {
    "PASS",
    "ERR_GM_INPUT",
    "ERR_NEWMARK_STABILITY",
    "ERR_ENERGY_DIVERGENCE",
}

ALLOWED_CACHE_PROFILE_REASON = {
    "PASS",
    "ERR_HOOK_EXEC",
    "ERR_NO_CACHE_SAFE_CHUNK",
    "ERR_INVALID_INPUT",
}

ALLOWED_P0_ENGINE_PERF_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_PROBE_FAIL",
    "ERR_TRACK_RUST_FAIL",
    "ERR_TRACK_PY_FAIL",
    "ERR_PROFILE_FIELDS",
    "ERR_SPEEDUP_FAIL",
}

ALLOWED_P0_CORE_GAP_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_P0_ENGINE_FAIL",
    "ERR_P0_ENGINE_PROFILE_FAIL",
    "ERR_P0_HIP_KERNEL_FAIL",
    "ERR_P0_BENCHMARK_BUILD_FAIL",
    "ERR_P0_BENCHMARK_KPI_FAIL",
    "ERR_P0_BENCHMARK_SUITE_FAIL",
    "ERR_P0_BENCHMARK_VALIDATION_FAIL",
    "ERR_P0_BENCHMARK_DATA_FAIL",
    "ERR_P0_BENCHMARK_FAIL",
}

ALLOWED_HIP_KERNEL_SMOKE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_HIP_COMPILER_MISSING",
    "ERR_HIP_BUILD_FAIL",
    "ERR_HIP_RUN_FAIL",
}

ALLOWED_NOISE_STRESS_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASE_SELECTION",
    "ERR_BENCHMARK_RUN",
    "ERR_METRIC_NAN",
    "ERR_ROBUSTNESS_FAIL",
}

ALLOWED_SOLVER_HIP_E2E_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_STRICT_PROBE_FAIL",
    "ERR_NONLINEAR_FRAME_GPU_FAIL",
    "ERR_NDTHA_GPU_FAIL",
    "ERR_TRACK_GPU_FAIL",
    "ERR_GPU_POLICY_FAIL",
}

ALLOWED_RC_BENCHMARK_LOCK_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES",
    "ERR_BENCHMARK_LOCK_FAIL",
}

ALLOWED_NDTHA_RESIDUAL_GATE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_NDTHA_REPORT",
    "ERR_RESIDUAL_TRACE",
    "ERR_RESIDUAL_HARD_LIMIT",
}

ALLOWED_SCALEOUT_IO_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_RUST_HIP_PATH_REQUIRED",
    "ERR_GPU_STRICT_FAIL",
    "ERR_PROBE_FAIL",
    "ERR_PROFILE_RUN_FAIL",
    "ERR_1M_GATE_FAIL",
}

ALLOWED_PHASE3_PIPELINE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CONVERSION_FAIL",
    "ERR_DIVERSITY_FAIL",
    "ERR_REAL_SOURCE_FAIL",
    "ERR_MIDAS_MGT_FAIL",
    "ERR_TOPOLOGY_FAIL",
    "ERR_BENCHMARK_FAIL",
    "ERR_NOISE_CONVERGENCE_FAIL",
    "ERR_PARTITION_SCALE_FAIL",
    "ERR_SYNC_STRESS_FAIL",
    "ERR_GPU_STRICT_FAIL",
    "ERR_NIGHTLY_10M_FAIL",
    "ERR_SUMMARY_FAIL",
}

ALLOWED_PARTITIONED_SCALEOUT_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_PARTITION_FAIL",
    "ERR_PROFILE_FAIL",
    "ERR_CI_MODE_FAIL",
    "ERR_REAL_GRAPH_FAIL",
}

ALLOWED_NOISE_CONVERGENCE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES",
    "ERR_CONVERGENCE_FAIL",
}

ALLOWED_COMMERCIAL_CSV_GATE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_BUILD_FAIL",
    "ERR_BENCHMARK_FAIL",
    "ERR_METRIC_SOURCE_FAIL",
    "ERR_MEMBER_FORCE_FAIL",
}

ALLOWED_MIDAS_MGT_CONVERSION_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_FILE_MISSING",
    "ERR_PARSE_FAIL",
    "ERR_SYNTHETIC_SOURCE",
    "ERR_SHELL_BEAM_MIX",
    "ERR_UNKNOWN_SECTION",
    "ERR_ELEMENT_SKIP_BUDGET",
}

ALLOWED_COMMERCIAL_READINESS_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_REAL_SOURCE_FAIL",
    "ERR_BENCHMARK_FAIL",
    "ERR_NOISE_ROBUSTNESS_FAIL",
    "ERR_NOISE_CONVERGENCE_FAIL",
    "ERR_PHASE_DYNAMICS_FAIL",
    "ERR_OOD_FAIL",
    "ERR_SCALEOUT_FAIL",
    "ERR_GPU_STRICT_FAIL",
    "ERR_COMMERCIAL_FAIL",
}

ALLOWED_REAL_SOURCE_MULTI_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES_MISSING",
    "ERR_REAL_SOURCE_FAIL",
}

ALLOWED_NIGHTLY_10M_REPRO_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_RUN_FAIL",
    "ERR_MISSING_10M_ROW",
    "ERR_VARIANCE_TOO_HIGH",
}

ALLOWED_NDTHA_LONG_PROFILE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_RUST_BACKEND_FAIL",
    "ERR_RUN_FAIL",
    "ERR_VARIANCE_FAIL",
}

ALLOWED_NONLINEAR_ENGINE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES",
    "ERR_TOP_DISP_SOURCE_FAIL",
    "ERR_ENGINE_FAIL",
    "ERR_VNV_FAIL",
}

ALLOWED_PUSHOVER_STRESS_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES",
    "ERR_ENGINE_FAIL",
    "ERR_PLASTICITY_NOT_TRIGGERED",
    "ERR_COLLAPSE_PATH_FAIL",
}

ALLOWED_NDTHA_STRESS_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES",
    "ERR_GM_INPUT",
    "ERR_PDELTA_DISABLED",
    "ERR_DYNAMICS_NOT_REVERSED",
    "ERR_RAYLEIGH_DAMPING_DISABLED",
    "ERR_ENGINE_FAIL",
    "ERR_NDTHA_CONVERGENCE_FAIL",
    "ERR_COLLAPSE_CUTOFF",
    "ERR_PLASTICITY_NOT_TRIGGERED",
}

ALLOWED_PBD_REVIEW_REASON = {
    "PASS",
}

ALLOWED_WIND_BENCHMARK_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_SOURCE_MANIFEST",
    "ERR_WIND_INPUT",
    "ERR_CASES",
    "ERR_ENGINE_FAIL",
    "ERR_VNV_FAIL",
}

ALLOWED_SSI_BOUNDARY_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES",
    "ERR_GM_INPUT",
    "ERR_SSI_MODEL",
    "ERR_ENGINE_FAIL",
    "ERR_VNV_FAIL",
}

ALLOWED_DAMPER_VALIDATION_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CATALOG",
    "ERR_SOURCE",
    "ERR_VNV_FAIL",
}

ALLOWED_KDS_COMPLIANCE_REASON = {
    "PASS",
    "ERR_INPUT",
    "ERR_KDS_COMPLIANCE_FAIL",
}

ALLOWED_CONSTRUCTION_SEQUENCE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES",
    "ERR_ENGINE_FAIL",
    "ERR_VNV_FAIL",
}

ALLOWED_FLEXIBLE_DIAPHRAGM_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES",
    "ERR_TOPOLOGY",
    "ERR_ENGINE_FAIL",
    "ERR_VNV_FAIL",
}

ALLOWED_REPRO_VERSION_LOCK_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CASES",
    "ERR_MODEL_HASH",
    "ERR_REPLAY_MISMATCH",
    "ERR_LOCK_WRITE",
}

ALLOWED_RELEASE_REGISTRY_REASON = {
    "PASS",
    "ERR_INPUT",
    "ERR_SOURCE_GATE",
    "ERR_SIGNATURE",
}

ALLOWED_GLOBAL_AUTHORITY_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_OPENSEES_FAIL",
    "ERR_HOLDOUT_LEAK",
    "ERR_METRICS_GENERATION_FAIL",
    "ERR_SAC_MISSING",
    "ERR_SAC_MIN_CASES",
    "ERR_SAC_FAIL",
    "ERR_NHERI_MISSING",
    "ERR_NHERI_MIN_CASES",
    "ERR_NHERI_FAIL",
}

ALLOWED_TOPOLOGY_GATE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_FILE_MISSING",
    "ERR_PARSE_FAIL",
    "ERR_SYNTHETIC_SOURCE",
    "ERR_SHELL_BEAM_MIX",
    "ERR_TOPOLOGY_COMPLEXITY",
}

ALLOWED_SYNC_STRESS_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_TOPOLOGY_GATE",
    "ERR_BACKEND_POLICY",
    "ERR_LEVEL_RUN",
    "ERR_SYNC_BUDGET",
}

ALLOWED_PHASEA_REASON = {
    "PASS",
    "ERR_DYNAMICS_DOMAIN_REPORT",
    "ERR_VEHICLE_SCHEMA",
    "ERR_TUNNEL_SCHEMA",
    "ERR_SOIL_TABLE",
    "ERR_MATERIAL_RULE_TABLE",
    "ERR_JSON_IO",
}

ALLOWED_TRACK_LF_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_CONVERGENCE",
    "ERR_ACCURACY",
}

ALLOWED_MOVING_LOAD_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_SOLVER_DIVERGENCE",
    "ERR_ENERGY_DIVERGENCE",
}

ALLOWED_VTI_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_COUPLING_DIVERGENCE",
    "ERR_DYNAMIC_DIVERGENCE",
}

ALLOWED_IRREGULARITY_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
}

ALLOWED_PHASEB_SUMMARY_REASON = {
    "PASS",
    "ERR_MODULE_FAIL",
}

ALLOWED_PHASED_TRACK_DATASET_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_DATASET_EMPTY",
    "ERR_RESIDUAL",
}

ALLOWED_PHASED_TUNNEL_DATASET_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_DATASET_EMPTY",
    "ERR_RESIDUAL",
}

ALLOWED_PHASED_ATTENTION_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_SHAPE",
}

ALLOWED_PHASED_TGNN_REASON = {
    "PASS",
    "ERR_DATASET_EMPTY",
    "ERR_METRIC_FAIL",
}

ALLOWED_PHASED_SUMMARY_REASON = {
    "PASS",
    "ERR_MODULE_FAIL",
}

ALLOWED_PHASEE_SUBSTRUCTURING_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_INTERFACE_MISMATCH",
    "ERR_COUPLING_STABILITY",
}

ALLOWED_PHASEE_ATTENUATION_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_MONOTONICITY",
}

ALLOWED_PHASEE_COMPLIANCE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_LIMIT_EXCEEDED",
}

ALLOWED_PHASEE_WHITEBOX_REASON = {
    "PASS",
    "ERR_METRIC_FAIL",
}

ALLOWED_PHASEE_SUMMARY_REASON = {
    "PASS",
    "ERR_MODULE_FAIL",
}

ALLOWED_PHASEF_L3_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_NO_CACHE_SAFE_CHUNK",
}

ALLOWED_PHASEF_PHASE_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_PHASE_NOT_IMPROVED",
}

ALLOWED_PHASEF_SOIL_OOD_REASON = {
    "PASS",
    "ERR_INVALID_INPUT",
    "ERR_OOD_GATE_FAIL",
}

ALLOWED_PHASEF_SUMMARY_REASON = {
    "PASS",
    "ERR_MODULE_FAIL",
}


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _is_finite_number(x: object) -> bool:
    try:
        v = float(x)
    except Exception:
        return False
    return math.isfinite(v)




def _validate_common_metadata(report: dict, label: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(report.get("schema_version"), str):
        errs.append(f"{label}.schema_version missing")
    if not isinstance(report.get("run_id"), str):
        errs.append(f"{label}.run_id missing")
    if not isinstance(report.get("generated_at"), str):
        errs.append(f"{label}.generated_at missing")
    return errs

def validate_smoke(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "smoke"))
    if "pass" not in report:
        errs.append("smoke.pass missing")
    if report.get("reason_code") not in ALLOWED_SMOKE_REASON:
        errs.append("smoke.reason_code invalid")
    if not isinstance(report.get("interface_version"), str):
        errs.append("smoke.interface_version missing")

    ingest = report.get("ingest")
    if not isinstance(ingest, dict):
        errs.append("smoke.ingest missing")
    else:
        if not isinstance(ingest.get("node_count"), int):
            errs.append("smoke.ingest.node_count invalid")
        if not isinstance(ingest.get("edge_count"), int):
            errs.append("smoke.ingest.edge_count invalid")

    inf = report.get("inference")
    if not isinstance(inf, dict):
        errs.append("smoke.inference missing")
    else:
        if inf.get("backend") not in {"python", "torch"}:
            errs.append("smoke.inference.backend invalid")
        if not isinstance(inf.get("processed_batches"), int):
            errs.append("smoke.inference.processed_batches invalid")
        if not isinstance(inf.get("processed_nodes"), int):
            errs.append("smoke.inference.processed_nodes invalid")
        if not isinstance(inf.get("model_api_version"), str):
            errs.append("smoke.inference.model_api_version missing")
    return errs


def validate_ci(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "ci"))
    if report.get("reason_code") not in ALLOWED_CI_REASON:
        errs.append("ci.reason_code invalid")
    for key in (
        "strict_rust_hip_pass",
        "host_copy_share_pass",
        "all_pass",
        "contract_artifacts_pass",
        "branching_contract_pass",
        "bifurcation_contract_pass",
        "rust_onnx_contract_pass",
        "winning_ticket_contract_pass",
        "rust_md3bead_parity_pass",
        "lj_mapping_contract_pass",
        "dynamic_time_history_pass",
        "cache_profile_pass",
        "p0_engine_perf_pass",
        "p0_core_gap_pass",
        "hip_kernel_smoke_pass",
        "noise_stress_pass",
        "scaleout_io_pass",
        "phase3_real_source_pass",
        "topology_gate_pass",
        "shell_beam_mix_pass",
        "partitioned_scaleout_pass",
        "sync_stress_pass",
        "noise_convergence_pass",
        "commercial_csv_gate_pass",
        "midas_mgt_conversion_pass",
        "commercial_readiness_pass",
        "real_source_multi_pass",
        "nonlinear_engine_pass",
        "pushover_stress_pass",
        "ndtha_stress_pass",
        "pbd_review_pass",
        "global_authority_gate_pass",
        "wind_benchmark_pass",
        "ssi_boundary_pass",
        "damper_validation_pass",
        "kds_frontend_pass",
        "construction_sequence_pass",
        "flexible_diaphragm_pass",
        "repro_version_lock_pass",
        "solver_hip_e2e_pass",
        "rc_benchmark_lock_pass",
        "gpu_strict_pass",
        "nightly_10m_pass",
        "nightly_10m_repro_pass",
        "ndtha_long_profile_pass",
        "phasea_contract_pass",
        "phaseb_track_contract_pass",
        "phased_multidomain_contract_pass",
        "phasee_integrated_contract_pass",
        "phasef_resilience_contract_pass",
    ):
        if not isinstance(report.get(key), bool):
            errs.append(f"ci.{key} invalid")
    for key in ("host_copy_share", "host_copy_share_limit"):
        if not _is_finite_number(report.get(key)):
            errs.append(f"ci.{key} invalid")
    if not isinstance(report.get("missing_contract_artifacts"), list):
        errs.append("ci.missing_contract_artifacts invalid")
    return errs


def validate_rca(report: dict) -> list[str]:
    errs: list[str] = []
    t = report.get("timing_breakdown_seconds")
    if not isinstance(t, dict):
        return ["rca.timing_breakdown_seconds missing"]
    for key in ("compute", "host_copy", "serialization"):
        if not _is_finite_number(t.get(key)):
            errs.append(f"rca.timing_breakdown_seconds.{key} invalid")
        elif float(t[key]) < 0:
            errs.append(f"rca.timing_breakdown_seconds.{key} negative")
    return errs




def validate_priority(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "priority"))
    if report.get("reason_code") not in ALLOWED_PRIORITY_REASON:
        errs.append("priority.reason_code invalid")
    for key in ("module1_zero_copy_bridge", "module2_krylov_projection", "module3_material_parser", "all_pass"):
        if not isinstance(report.get(key), bool):
            errs.append(f"priority.{key} invalid")
    md = report.get("module_metadata")
    if not isinstance(md, dict):
        errs.append("priority.module_metadata missing")
    else:
        if not isinstance(md.get("metadata_compatible"), bool):
            errs.append("priority.module_metadata.metadata_compatible invalid")
    return errs

def validate_dyn(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "dyn"))
    if report.get("reason_code") not in ALLOWED_DYN_REASON:
        errs.append("dyn.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("dyn.contract_pass invalid")
    if not isinstance(report.get("interface_version"), str):
        errs.append("dyn.interface_version missing")
    return errs


def validate_pgat(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "pgat"))
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("pgat.contract_pass invalid")
    if not isinstance(report.get("attention_policy"), dict):
        errs.append("pgat.attention_policy missing")
    return errs


def validate_subproj(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "subproj"))
    if report.get("projection_mode") != "subgraph_divide_and_conquer":
        errs.append("subproj.projection_mode invalid")
    if not isinstance(report.get("subgraph_count"), int):
        errs.append("subproj.subgraph_count invalid")
    return errs


def validate_soa(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "soa"))
    if report.get("layout") != "SoA":
        errs.append("soa.layout invalid")
    if not isinstance(report.get("layout_pass"), bool):
        errs.append("soa.layout_pass invalid")
    return errs


def validate_physics_residual(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "physics_residual"))
    if report.get("reason_code") not in ALLOWED_PHYSICS_RESIDUAL_REASON:
        errs.append("physics_residual.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("physics_residual.contract_pass invalid")

    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("physics_residual.metrics missing")
    else:
        for key in ("equilibrium_residual_norm", "boundary_violation_ratio", "damping_alpha", "damping_beta"):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"physics_residual.metrics.{key} invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("physics_residual.checks missing")
    else:
        for key in ("eq_ok", "boundary_ok", "damping_ok", "energy_monotonicity_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"physics_residual.checks.{key} invalid")
    return errs


def validate_meta_learning(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "meta_learning"))
    if report.get("reason_code") not in ALLOWED_META_LEARNING_REASON:
        errs.append("meta_learning.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("meta_learning.contract_pass invalid")
    if not isinstance(report.get("task_count"), int):
        errs.append("meta_learning.task_count invalid")

    tasks = report.get("tasks")
    if not isinstance(tasks, list) or len(tasks) == 0:
        errs.append("meta_learning.tasks invalid")
    else:
        for idx, task in enumerate(tasks):
            if not isinstance(task, dict):
                errs.append(f"meta_learning.tasks[{idx}] invalid")
                continue
            for key in ("task_id", "topology_type", "hazard_type", "support_profile", "split", "ood_tag", "target_zone"):
                if key not in task:
                    errs.append(f"meta_learning.tasks[{idx}].{key} missing")
            tz = task.get("target_zone")
            if not isinstance(tz, dict):
                errs.append(f"meta_learning.tasks[{idx}].target_zone invalid")
            else:
                node_ids = tz.get("node_ids")
                if not isinstance(node_ids, list) or len(node_ids) == 0:
                    errs.append(f"meta_learning.tasks[{idx}].target_zone.node_ids invalid")
    if not isinstance(report.get("meta_ood_generalization_pass"), bool):
        errs.append("meta_learning.meta_ood_generalization_pass invalid")
    return errs


def validate_buckling(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "buckling"))
    if report.get("reason_code") not in ALLOWED_BUCKLING_REASON:
        errs.append("buckling.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("buckling.contract_pass invalid")
    if not _is_finite_number(report.get("critical_load_factor")):
        errs.append("buckling.critical_load_factor invalid")
    if not isinstance(report.get("mode_count"), int):
        errs.append("buckling.mode_count invalid")
    return errs


def validate_benchmark(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "benchmark"))
    if report.get("reason_code") not in ALLOWED_BENCHMARK_REASON:
        errs.append("benchmark.reason_code invalid")
    for key in ("contract_pass", "kpi_pass"):
        if not isinstance(report.get(key), bool):
            errs.append(f"benchmark.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("benchmark.metrics missing")
    else:
        for key in ("drift_error_pct", "base_shear_error_pct", "mode_shape_mac", "buckling_factor_error_pct"):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"benchmark.metrics.{key} invalid")
    return errs



def validate_branching(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "branching"))
    if report.get("reason_code") not in ALLOWED_BRANCHING_REASON:
        errs.append("branching.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("branching.contract_pass invalid")
    if not isinstance(report.get("uses_backprop"), bool):
        errs.append("branching.uses_backprop invalid")
    if report.get("uses_backprop") is not False:
        errs.append("branching.uses_backprop must be false")
    if not isinstance(report.get("branch_count"), int):
        errs.append("branching.branch_count invalid")
    return errs


def validate_bifurcation(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "bifurcation"))
    if report.get("reason_code") not in ALLOWED_BIFURCATION_REASON:
        errs.append("bifurcation.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("bifurcation.contract_pass invalid")
    trig = report.get("trigger")
    if not isinstance(trig, dict):
        errs.append("bifurcation.trigger missing")
    else:
        if not isinstance(trig.get("triggered"), bool):
            errs.append("bifurcation.trigger.triggered invalid")
        if trig.get("trigger_step") is not None and not isinstance(trig.get("trigger_step"), int):
            errs.append("bifurcation.trigger.trigger_step invalid")
    return errs


def validate_rust_onnx(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "rust_onnx"))
    if report.get("reason_code") not in ALLOWED_RUST_ONNX_REASON:
        errs.append("rust_onnx.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("rust_onnx.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("rust_onnx.checks missing")
    else:
        for key in ("weights_as_dynamic_input", "execution_provider_rocm", "single_binary_deployment", "rayon_async_branch_inference", "dlpack_python_bridge_removed"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"rust_onnx.checks.{key} invalid")
    return errs


def validate_winning_ticket(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "winning_ticket"))
    if report.get("reason_code") not in ALLOWED_WINNING_TICKET_REASON:
        errs.append("winning_ticket.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("winning_ticket.contract_pass invalid")
    if not isinstance(report.get("uses_backprop"), bool):
        errs.append("winning_ticket.uses_backprop invalid")
    if report.get("uses_backprop") is not True:
        errs.append("winning_ticket.uses_backprop must be true")

    sel = report.get("selection")
    if not isinstance(sel, dict):
        errs.append("winning_ticket.selection missing")
    else:
        strategy = sel.get("strategy")
        if strategy != "topk_weighted_backprop":
            errs.append("winning_ticket.selection.strategy invalid")
        top_k = sel.get("top_k")
        if not isinstance(top_k, int) or top_k < 2:
            errs.append("winning_ticket.selection.top_k invalid")
        ids = sel.get("selected_branch_ids")
        if not isinstance(ids, list) or len(ids) == 0:
            errs.append("winning_ticket.selection.selected_branch_ids invalid")
        else:
            if not all(isinstance(v, int) for v in ids):
                errs.append("winning_ticket.selection.selected_branch_ids must be int list")
            if isinstance(top_k, int) and len(ids) != top_k:
                errs.append("winning_ticket.selection.selected_branch_ids length mismatch")
        ws = sel.get("normalized_weights")
        if not isinstance(ws, list) or len(ws) == 0:
            errs.append("winning_ticket.selection.normalized_weights invalid")
        else:
            if not all(_is_finite_number(v) for v in ws):
                errs.append("winning_ticket.selection.normalized_weights non-numeric")
            if isinstance(top_k, int) and len(ws) != top_k:
                errs.append("winning_ticket.selection.normalized_weights length mismatch")

    tb = report.get("targeted_backprop")
    if not isinstance(tb, dict):
        errs.append("winning_ticket.targeted_backprop missing")
    else:
        top_k = int(sel.get("top_k", 0)) if isinstance(sel, dict) else 0
        if int(tb.get("graph_count", 0)) != top_k:
            errs.append("winning_ticket.targeted_backprop.graph_count must match top_k")
        if tb.get("weighted_aggregation") is not True:
            errs.append("winning_ticket.targeted_backprop.weighted_aggregation must be true")
        if not isinstance(tb.get("success"), bool):
            errs.append("winning_ticket.targeted_backprop.success invalid")
    return errs


def validate_rust_parity(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "rust_parity"))
    if report.get("reason_code") not in ALLOWED_RUST_PARITY_REASON:
        errs.append("rust_parity.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("rust_parity.contract_pass invalid")

    step1 = report.get("step1_parity")
    if not isinstance(step1, dict):
        errs.append("rust_parity.step1_parity missing")
    else:
        if not isinstance(step1.get("pass"), bool):
            errs.append("rust_parity.step1_parity.pass invalid")
        if not isinstance(step1.get("rows"), list):
            errs.append("rust_parity.step1_parity.rows invalid")

    step5 = report.get("step5_parity")
    if not isinstance(step5, dict):
        errs.append("rust_parity.step5_parity missing")
    else:
        if not isinstance(step5.get("pass"), bool):
            errs.append("rust_parity.step5_parity.pass invalid")
        if not isinstance(step5.get("rows"), list):
            errs.append("rust_parity.step5_parity.rows invalid")
    return errs


def validate_lj_mapping(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "lj_mapping"))
    if report.get("reason_code") not in ALLOWED_LJ_MAPPING_REASON:
        errs.append("lj_mapping.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("lj_mapping.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("lj_mapping.checks missing")
    else:
        for key in ("yield_detected", "yield_strain_pass", "post_yield_softening_pass", "energy_dissipation_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"lj_mapping.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("lj_mapping.metrics missing")
    else:
        for key in ("peak_force_before_yield_n", "post_yield_peak_force_n", "dissipated_energy_j"):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"lj_mapping.metrics.{key} invalid")
    return errs


def validate_dynamic_time_history(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "dynamic_time_history"))
    if report.get("reason_code") not in ALLOWED_DYNAMIC_TIME_HISTORY_REASON:
        errs.append("dynamic_time_history.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("dynamic_time_history.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("dynamic_time_history.checks missing")
    else:
        for key in ("finite_response", "non_divergent_response", "equilibrium_residual_pass", "energy_balance_pass", "newmark_stability_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"dynamic_time_history.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("dynamic_time_history.metrics missing")
    else:
        for key in ("max_displacement_m", "equilibrium_residual_ratio", "energy_balance_relative_error", "peak_base_shear_n"):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"dynamic_time_history.metrics.{key} invalid")
    return errs


def validate_cache_profile(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "cache_profile"))
    if report.get("reason_code") not in ALLOWED_CACHE_PROFILE_REASON:
        errs.append("cache_profile.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("cache_profile.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("cache_profile.checks missing")
    else:
        for key in ("microbatch_available",):
            if not isinstance(checks.get(key), bool):
                errs.append(f"cache_profile.checks.{key} invalid")
    if not isinstance(report.get("scenarios"), list):
        errs.append("cache_profile.scenarios invalid")
    if report.get("recommended") is not None and not isinstance(report.get("recommended"), dict):
        errs.append("cache_profile.recommended invalid")
    return errs


def validate_p0_engine_perf(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "p0_engine_perf"))
    if report.get("reason_code") not in ALLOWED_P0_ENGINE_PERF_REASON:
        errs.append("p0_engine_perf.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("p0_engine_perf.contract_pass invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("p0_engine_perf.checks missing")
    else:
        for key in ("probe_pass", "track_rust_pass", "track_python_pass", "has_performance_fields", "speedup_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"p0_engine_perf.checks.{key} invalid")

    perf = report.get("performance")
    if not isinstance(perf, dict):
        errs.append("p0_engine_perf.performance missing")
    else:
        zc = perf.get("zero_copy_timing_breakdown_seconds")
        if not isinstance(zc, dict):
            errs.append("p0_engine_perf.performance.zero_copy_timing_breakdown_seconds invalid")
        else:
            for key in ("compute", "host_copy", "serialization"):
                if not _is_finite_number(zc.get(key)):
                    errs.append(f"p0_engine_perf.performance.zero_copy_timing_breakdown_seconds.{key} invalid")

        for key in ("rust_elapsed_seconds", "python_elapsed_seconds", "speedup_python_over_rust"):
            block = perf.get(key)
            if not isinstance(block, dict):
                errs.append(f"p0_engine_perf.performance.{key} invalid")
                continue
            for theory in ("euler", "timoshenko"):
                if not _is_finite_number(block.get(theory)):
                    errs.append(f"p0_engine_perf.performance.{key}.{theory} invalid")

    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("p0_engine_perf.artifacts missing")
    else:
        for key in ("probe", "track_rust", "track_python"):
            if not isinstance(artifacts.get(key), str):
                errs.append(f"p0_engine_perf.artifacts.{key} invalid")

    if not isinstance(report.get("steps"), list):
        errs.append("p0_engine_perf.steps invalid")
    return errs


def validate_p0_core_gap(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "p0_core_gap"))
    if report.get("reason_code") not in ALLOWED_P0_CORE_GAP_REASON:
        errs.append("p0_core_gap.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("p0_core_gap.contract_pass invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("p0_core_gap.checks missing")
    else:
        for key in ("p0_1_rust_engine_pass", "p0_1_engine_profile_pass", "p0_2_public_benchmark_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"p0_core_gap.checks.{key} invalid")

    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("p0_core_gap.artifacts missing")
    else:
        for key in ("probe", "track", "perf", "accuracy"):
            if not isinstance(artifacts.get(key), str):
                errs.append(f"p0_core_gap.artifacts.{key} invalid")

    if not isinstance(report.get("steps"), list):
        errs.append("p0_core_gap.steps invalid")
    return errs


def validate_hip_kernel_smoke(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "hip_kernel_smoke"))
    if report.get("reason_code") not in ALLOWED_HIP_KERNEL_SMOKE_REASON:
        errs.append("hip_kernel_smoke.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("hip_kernel_smoke.contract_pass invalid")
    if not isinstance(report.get("inputs"), dict):
        errs.append("hip_kernel_smoke.inputs missing")

    if bool(report.get("contract_pass", False)):
        if not isinstance(report.get("backend"), dict):
            errs.append("hip_kernel_smoke.backend missing")
        for block_name in ("build", "run"):
            block = report.get(block_name)
            if not isinstance(block, dict):
                errs.append(f"hip_kernel_smoke.{block_name} missing")
                continue
            # Backward-compatible validator:
            # 1) legacy flat schema: build/run contain seconds + return_code
            # 2) multi-kernel schema: build/run contain primary[/secondary] blocks
            has_flat = _is_finite_number(block.get("seconds")) and _is_finite_number(block.get("return_code"))
            if has_flat:
                continue
            primary = block.get("primary")
            if not isinstance(primary, dict):
                errs.append(f"hip_kernel_smoke.{block_name}.seconds invalid")
                errs.append(f"hip_kernel_smoke.{block_name}.return_code invalid")
                continue
            if not _is_finite_number(primary.get("seconds")):
                errs.append(f"hip_kernel_smoke.{block_name}.seconds invalid")
            if not _is_finite_number(primary.get("return_code")):
                errs.append(f"hip_kernel_smoke.{block_name}.return_code invalid")
        checks = report.get("checks")
        if not isinstance(checks, dict):
            errs.append("hip_kernel_smoke.checks missing")
        else:
            for key in ("hip_compiler_present", "build_pass", "run_pass", "kernel_backend_pass"):
                if not isinstance(checks.get(key), bool):
                    errs.append(f"hip_kernel_smoke.checks.{key} invalid")
    return errs


def validate_solver_hip_e2e(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "solver_hip_e2e"))
    if report.get("reason_code") not in ALLOWED_SOLVER_HIP_E2E_REASON:
        errs.append("solver_hip_e2e.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("solver_hip_e2e.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("solver_hip_e2e.checks missing")
    else:
        for key in (
            "strict_probe_pass",
            "nonlinear_frame_gpu_pass",
            "ndtha_gpu_pass",
            "track_gpu_pass",
            "all_main_loops_gpu_pass",
            "no_cpu_backend_pass",
            "no_cpu_required_pass",
            "no_cpu_fallback_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"solver_hip_e2e.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("solver_hip_e2e.summary missing")
    else:
        for key in ("solver_count", "gpu_solver_count", "device_residency_ratio_min", "hip_kernel_invocation_count_total"):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"solver_hip_e2e.summary.{key} invalid")
    rows = report.get("solver_rows")
    if not isinstance(rows, list):
        errs.append("solver_hip_e2e.solver_rows invalid")
    else:
        for idx, row in enumerate(rows[:8]):
            if not isinstance(row, dict):
                errs.append(f"solver_hip_e2e.solver_rows[{idx}] invalid")
                continue
            runtime = row.get("runtime")
            if not isinstance(runtime, dict):
                errs.append(f"solver_hip_e2e.solver_rows[{idx}].runtime invalid")
                continue
            for key in (
                "main_loop_backend",
                "hip_kernel_invocation_count",
                "cpu_backend",
                "cpu_required",
                "cpu_fallback_used",
                "host_copy_bytes",
                "device_residency_ratio",
                "gpu_main_loop_pass",
            ):
                if key == "main_loop_backend":
                    if not isinstance(runtime.get(key), str):
                        errs.append(f"solver_hip_e2e.solver_rows[{idx}].runtime.{key} invalid")
                elif key in {"cpu_backend", "cpu_required", "cpu_fallback_used", "gpu_main_loop_pass"}:
                    if not isinstance(runtime.get(key), bool):
                        errs.append(f"solver_hip_e2e.solver_rows[{idx}].runtime.{key} invalid")
                else:
                    if not _is_finite_number(runtime.get(key)):
                        errs.append(f"solver_hip_e2e.solver_rows[{idx}].runtime.{key} invalid")
    return errs


def validate_rc_benchmark_lock(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "rc_benchmark_lock"))
    if report.get("reason_code") not in ALLOWED_RC_BENCHMARK_LOCK_REASON:
        errs.append("rc_benchmark_lock.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("rc_benchmark_lock.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("rc_benchmark_lock.checks missing")
    else:
        for key in (
            "case_count_pass",
            "finite_pass",
            "all_ranges_pass",
            "cracking_case_pass",
            "bond_slip_case_pass",
            "creep_case_pass",
            "slab_wall_case_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"rc_benchmark_lock.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("rc_benchmark_lock.summary missing")
    else:
        for key in ("case_count", "family_count"):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"rc_benchmark_lock.summary.{key} invalid")
        if not isinstance(summary.get("families"), list):
            errs.append("rc_benchmark_lock.summary.families invalid")
    if not isinstance(report.get("rows"), list):
        errs.append("rc_benchmark_lock.rows invalid")
    return errs


def validate_noise_stress(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "noise_stress"))
    if report.get("reason_code") not in ALLOWED_NOISE_STRESS_REASON:
        errs.append("noise_stress.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("noise_stress.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("noise_stress.checks missing")
    else:
        for key in ("has_required_case_count", "noise_sweep_complete", "finite_metrics", "high_noise_available", "high_noise_degradation_detected", "robustness_budget_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"noise_stress.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("noise_stress.summary missing")
    else:
        for key in ("scenario_count_expected", "scenario_count_actual", "selected_case_count"):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"noise_stress.summary.{key} invalid")
    if not isinstance(report.get("scenario_rows"), list):
        errs.append("noise_stress.scenario_rows invalid")
    if not isinstance(report.get("steps"), list):
        errs.append("noise_stress.steps invalid")
    return errs


def validate_scaleout_io(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "scaleout_io"))
    if report.get("reason_code") not in ALLOWED_SCALEOUT_IO_REASON:
        errs.append("scaleout_io.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("scaleout_io.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("scaleout_io.checks missing")
    else:
        for key in ("probe_pass", "rust_hip_cmd_policy_pass", "profile_scenarios_present", "profiles_all_pass", "has_1m_plus", "scaleout_1m_microbatch_pass", "scaleout_1m_branch_latency_pass", "scaleout_1m_fullbatch_miss_expected", "saturation_detected_above_1m", "monotonic_working_set"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"scaleout_io.checks.{key} invalid")
    probe = report.get("probe")
    if not isinstance(probe, dict):
        errs.append("scaleout_io.probe missing")
    else:
        for key in ("probe_pass", "strict_pass", "cpu_fallback_used"):
            if not isinstance(probe.get(key), bool):
                errs.append(f"scaleout_io.probe.{key} invalid")
        for key in ("host_copy_share", "host_copy_share_limit"):
            if not _is_finite_number(probe.get(key)):
                errs.append(f"scaleout_io.probe.{key} invalid")
    if not isinstance(report.get("level_rows"), list):
        errs.append("scaleout_io.level_rows invalid")
    if not isinstance(report.get("steps"), list):
        errs.append("scaleout_io.steps invalid")
    return errs


def validate_phase3_real_source(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phase3_pipeline"))
    if report.get("reason_code") not in ALLOWED_PHASE3_PIPELINE_REASON:
        errs.append("phase3_pipeline.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phase3_pipeline.contract_pass invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phase3_pipeline.checks missing")
    else:
        for key in (
            "real_source_verified",
            "sample_source_blocked",
            "case_diversity_pass",
            "topology_gate_pass",
            "shell_beam_mix_pass",
            "benchmark_pass",
            "noise_convergence_pass",
            "noise_seed_diversity_pass",
            "noise_case_diversity_pass",
            "noise_stagewise_pass",
            "sync_stress_pass",
            "sync_backend_policy_pass",
            "sync_inline_native_smoke_pass",
            "gpu_strict_pass",
            "pr_scale_pass",
            "nightly_scale_pass",
            "projection_ratio_pass",
            "graph_source_is_real",
            "partition_quality_threshold_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phase3_pipeline.checks.{key} invalid")

    reports = report.get("reports")
    if not isinstance(reports, dict):
        errs.append("phase3_pipeline.reports missing")
    else:
        for key in (
            "conversion",
            "source_manifest",
            "topology",
            "benchmark",
            "comparison",
            "noise_convergence",
            "partitioned_scaleout",
            "sync_stress",
        ):
            if not isinstance(reports.get(key), str):
                errs.append(f"phase3_pipeline.reports.{key} invalid")

    if not isinstance(report.get("steps"), list):
        errs.append("phase3_pipeline.steps invalid")
    return errs


def validate_partitioned_scaleout(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "partitioned_scaleout"))
    if report.get("reason_code") not in ALLOWED_PARTITIONED_SCALEOUT_REASON:
        errs.append("partitioned_scaleout.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("partitioned_scaleout.contract_pass invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("partitioned_scaleout.checks missing")
    else:
        for key in (
            "pr_scale_pass",
            "nightly_scale_pass",
            "gpu_strict_required",
            "gpu_strict_pass",
            "on_scaling_regression_pass",
            "real_graph_required",
            "real_graph_used",
            "projection_ratio_enforced",
            "projection_ratio_pass",
            "partition_quality_threshold_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"partitioned_scaleout.checks.{key} invalid")

    rows = report.get("level_rows")
    if not isinstance(rows, list):
        errs.append("partitioned_scaleout.level_rows invalid")
    else:
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                errs.append(f"partitioned_scaleout.level_rows[{idx}] invalid")
                continue
            for key in (
                "node_count",
                "profiled_node_count",
                "graph_source_real",
                "real_graph_used",
                "partition_contract_pass",
                "partition_quality_threshold_pass",
                "scaleout_contract_pass",
                "scaleout_gpu_strict_pass",
                "scaleout_1m_microbatch_pass",
                "projection_ratio",
                "projection_ratio_pass",
            ):
                if key not in row:
                    errs.append(f"partitioned_scaleout.level_rows[{idx}].{key} missing")

    reg = report.get("complexity_regression")
    if reg is not None:
        if not isinstance(reg, dict):
            errs.append("partitioned_scaleout.complexity_regression invalid")
        else:
            for key in ("memory_loglog_slope", "latency_loglog_slope"):
                val = reg.get(key)
                if val is not None and not _is_finite_number(val):
                    errs.append(f"partitioned_scaleout.complexity_regression.{key} invalid")

    if not isinstance(report.get("steps"), list):
        errs.append("partitioned_scaleout.steps invalid")
    return errs


def validate_noise_convergence(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "noise_convergence"))
    if report.get("reason_code") not in ALLOWED_NOISE_CONVERGENCE_REASON:
        errs.append("noise_convergence.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("noise_convergence.contract_pass invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("noise_convergence.checks missing")
    else:
        for key in (
            "has_required_seeds",
            "has_seed_diversity",
            "includes_plus_minus_10",
            "includes_plus_minus_5",
            "case_diversity_pass",
            "stagewise_execution_pass",
            "all_converged",
            "scenario_count_nonzero",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"noise_convergence.checks.{key} invalid")

    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("noise_convergence.summary missing")
    else:
        for key in ("selected_case_count", "seed_count", "noise_level_count", "scenario_count", "fail_count"):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"noise_convergence.summary.{key} invalid")

    if not isinstance(report.get("rows"), list):
        errs.append("noise_convergence.rows invalid")
    if not isinstance(report.get("stage_rows"), list):
        errs.append("noise_convergence.stage_rows invalid")
    return errs


def validate_commercial_csv_gate(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "commercial_csv_gate"))
    if report.get("reason_code") not in ALLOWED_COMMERCIAL_CSV_GATE_REASON:
        errs.append("commercial_csv_gate.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("commercial_csv_gate.contract_pass invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("commercial_csv_gate.checks missing")
    else:
        for key in (
            "build_cases_pass",
            "benchmark_pass",
            "metric_source_pass",
            "drift_within_5pct",
            "base_shear_within_5pct",
            "buckling_within_5pct",
            "mac_above_095",
            "member_force_metric_present",
            "member_force_soft_accept_pass",
            "member_force_hard_pass",
            "member_force_components_5d_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"commercial_csv_gate.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("commercial_csv_gate.metrics missing")
    else:
        for key in (
            "drift_error_pct",
            "base_shear_error_pct",
            "mode_shape_mac",
            "buckling_factor_error_pct",
            "member_force_error_pct_p95",
            "member_force_error_pct_max",
            "member_force_soft_accept_case_ratio",
            "member_force_component_count",
        ):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"commercial_csv_gate.metrics.{key} invalid")
    if not isinstance(report.get("steps"), list):
        errs.append("commercial_csv_gate.steps invalid")
    return errs


def validate_midas_mgt_conversion(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "midas_mgt_conversion"))
    if report.get("reason_code") not in ALLOWED_MIDAS_MGT_CONVERSION_REASON:
        errs.append("midas_mgt_conversion.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("midas_mgt_conversion.contract_pass invalid")

    source = report.get("source_provenance")
    if not isinstance(source, dict):
        errs.append("midas_mgt_conversion.source_provenance missing")
    else:
        if source.get("source_family") != "midas_mgt":
            errs.append("midas_mgt_conversion.source_provenance.source_family invalid")
        if not isinstance(source.get("path"), str):
            errs.append("midas_mgt_conversion.source_provenance.path invalid")
        if not isinstance(source.get("sha256"), str):
            errs.append("midas_mgt_conversion.source_provenance.sha256 invalid")
        if not _is_finite_number(source.get("size_bytes")):
            errs.append("midas_mgt_conversion.source_provenance.size_bytes invalid")

    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("midas_mgt_conversion.metrics missing")
    else:
        for key in (
            "line_count",
            "section_count",
            "node_count",
            "element_count",
            "element_rows_total",
            "element_rows_skipped",
            "element_skip_ratio",
            "edge_count_undirected",
            "beam_element_count",
            "shell_element_count",
        ):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"midas_mgt_conversion.metrics.{key} invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("midas_mgt_conversion.checks missing")
    else:
        for key in (
            "has_nodes",
            "has_elements",
            "shell_beam_mix_pass",
            "synthetic_source_blocked",
            "unknown_section_policy_pass",
            "strict_element_slot_parse",
            "rigid_link_resolution_applied",
            "dummy_node_removed",
            "element_skip_budget_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"midas_mgt_conversion.checks.{key} invalid")

    parser_diag = report.get("parser_diagnostics")
    if not isinstance(parser_diag, dict):
        errs.append("midas_mgt_conversion.parser_diagnostics missing")
    else:
        for key in ("known_section_count", "unknown_section_count", "unknown_row_total", "typed_row_total"):
            if not _is_finite_number(parser_diag.get(key)):
                errs.append(f"midas_mgt_conversion.parser_diagnostics.{key} invalid")
        if not isinstance(parser_diag.get("unknown_sections"), list):
            errs.append("midas_mgt_conversion.parser_diagnostics.unknown_sections invalid")
        if not isinstance(parser_diag.get("unknown_section_row_count"), dict):
            errs.append("midas_mgt_conversion.parser_diagnostics.unknown_section_row_count invalid")
        row_parse = parser_diag.get("row_parse")
        if not isinstance(row_parse, dict):
            errs.append("midas_mgt_conversion.parser_diagnostics.row_parse invalid")
        else:
            for key in (
                "node_rows",
                "node_rows_parsed",
                "node_rows_skipped",
                "element_rows",
                "element_rows_parsed",
                "element_rows_skipped",
                "element_skip_ratio",
            ):
                if not _is_finite_number(row_parse.get(key)):
                    errs.append(f"midas_mgt_conversion.parser_diagnostics.row_parse.{key} invalid")
        if not isinstance(parser_diag.get("element_skip_reason_count"), dict):
            errs.append("midas_mgt_conversion.parser_diagnostics.element_skip_reason_count invalid")
        if not isinstance(parser_diag.get("unsupported_element_type_count"), dict):
            errs.append("midas_mgt_conversion.parser_diagnostics.unsupported_element_type_count invalid")
        if not isinstance(parser_diag.get("unresolved_elements_head"), list):
            errs.append("midas_mgt_conversion.parser_diagnostics.unresolved_elements_head invalid")

    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("midas_mgt_conversion.artifacts missing")
    else:
        for key in ("json_out", "npz_out"):
            if not isinstance(artifacts.get(key), str):
                errs.append(f"midas_mgt_conversion.artifacts.{key} invalid")
        npz_summary = artifacts.get("npz_summary")
        if not isinstance(npz_summary, dict):
            errs.append("midas_mgt_conversion.artifacts.npz_summary invalid")
        else:
            for key in ("node_count", "edge_count_directed", "element_count", "elem_conn_index_count"):
                if not _is_finite_number(npz_summary.get(key)):
                    errs.append(f"midas_mgt_conversion.artifacts.npz_summary.{key} invalid")
    return errs


def validate_commercial_readiness(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "commercial_readiness"))
    if report.get("reason_code") not in ALLOWED_COMMERCIAL_READINESS_REASON:
        errs.append("commercial_readiness.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("commercial_readiness.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("commercial_readiness.checks missing")
    else:
        for key in (
            "real_source_pass",
            "accuracy_pass",
            "noise_robustness_pass",
            "noise_convergence_pass",
            "phase_dynamics_pass",
            "ood_safety_pass",
            "scaleout_pass",
            "gpu_strict_pass",
            "on_scaling_regression_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"commercial_readiness.checks.{key} invalid")
    inputs = report.get("inputs")
    if not isinstance(inputs, dict):
        errs.append("commercial_readiness.inputs missing")
    else:
        if not isinstance(inputs.get("forbid_toy_cases"), bool):
            errs.append("commercial_readiness.inputs.forbid_toy_cases invalid")
    if not isinstance(report.get("model_rows"), list):
        errs.append("commercial_readiness.model_rows invalid")
    return errs


def validate_real_source_multi_gate(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "real_source_multi"))
    if report.get("reason_code") not in ALLOWED_REAL_SOURCE_MULTI_REASON:
        errs.append("real_source_multi.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("real_source_multi.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("real_source_multi.checks missing")
    else:
        for key in ("cases_present_pass", "all_real_source_pass", "all_toy_free_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"real_source_multi.checks.{key} invalid")
    if not isinstance(report.get("rows"), list):
        errs.append("real_source_multi.rows invalid")
    return errs


def validate_nightly_10m_repro(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "nightly_10m_repro"))
    if report.get("reason_code") not in ALLOWED_NIGHTLY_10M_REPRO_REASON:
        errs.append("nightly_10m_repro.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("nightly_10m_repro.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("nightly_10m_repro.checks missing")
    else:
        for key in ("run_count_sufficient", "all_runs_pass", "has_10m_rows", "latency_cov_pass", "working_set_cov_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"nightly_10m_repro.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("nightly_10m_repro.summary missing")
    else:
        for key in ("run_count",):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"nightly_10m_repro.summary.{key} invalid")
    if not isinstance(report.get("rows"), list):
        errs.append("nightly_10m_repro.rows invalid")
    return errs


def validate_ndtha_long_profile(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "ndtha_long_profile"))
    if report.get("reason_code") not in ALLOWED_NDTHA_LONG_PROFILE_REASON:
        errs.append("ndtha_long_profile.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("ndtha_long_profile.contract_pass invalid")
    if not isinstance(report.get("inputs"), dict):
        errs.append("ndtha_long_profile.inputs missing")

    checks = report.get("checks")
    summary = report.get("summary")
    rows = report.get("rows")
    if report.get("reason_code") != "ERR_INVALID_INPUT":
        if not isinstance(checks, dict):
            errs.append("ndtha_long_profile.checks missing")
        else:
            for key in ("all_runs_pass", "rust_backend_all_runs_pass", "elapsed_cov_pass", "peak_vram_cov_pass"):
                if not isinstance(checks.get(key), bool):
                    errs.append(f"ndtha_long_profile.checks.{key} invalid")
        if not isinstance(summary, dict):
            errs.append("ndtha_long_profile.summary missing")
        else:
            for key in ("elapsed_wall_s_mean", "elapsed_wall_s_cov", "peak_vram_mb_mean", "peak_vram_mb_cov"):
                if not _is_finite_number(summary.get(key)):
                    errs.append(f"ndtha_long_profile.summary.{key} invalid")
        if not isinstance(rows, list):
            errs.append("ndtha_long_profile.rows invalid")
    return errs


def validate_nonlinear_engine(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "nonlinear_engine"))
    if report.get("reason_code") not in ALLOWED_NONLINEAR_ENGINE_REASON:
        errs.append("nonlinear_engine.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("nonlinear_engine.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("nonlinear_engine.checks missing")
    else:
        for key in (
            "metric_source_pass",
            "rust_backend_used_pass",
            "all_cases_converged",
            "drift_p95_pass",
            "base_shear_p95_pass",
            "top_disp_metric_source_available",
            "top_disp_metric_source_required_pass",
            "top_disp_p95_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"nonlinear_engine.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("nonlinear_engine.summary missing")
    else:
        for key in (
            "case_count",
            "drift_error_pct_mean",
            "drift_error_pct_p95",
            "base_shear_error_pct_mean",
            "base_shear_error_pct_p95",
        ):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"nonlinear_engine.summary.{key} invalid")
        top_mean = summary.get("top_disp_error_pct_mean")
        top_p95 = summary.get("top_disp_error_pct_p95")
        if top_mean is not None and not _is_finite_number(top_mean):
            errs.append("nonlinear_engine.summary.top_disp_error_pct_mean invalid")
        if top_p95 is not None and not _is_finite_number(top_p95):
            errs.append("nonlinear_engine.summary.top_disp_error_pct_p95 invalid")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("nonlinear_engine.artifacts missing")
    else:
        for key in ("report_json", "case_metrics_npz_out"):
            val = artifacts.get(key)
            if not isinstance(val, str):
                errs.append(f"nonlinear_engine.artifacts.{key} invalid")
                continue
            if not Path(val).exists():
                errs.append(f"nonlinear_engine.artifacts.{key} missing")
    if not isinstance(report.get("rows"), list):
        errs.append("nonlinear_engine.rows invalid")
    return errs


def validate_pushover_stress(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "pushover_stress"))
    if report.get("reason_code") not in ALLOWED_PUSHOVER_STRESS_REASON:
        errs.append("pushover_stress.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("pushover_stress.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("pushover_stress.checks missing")
    else:
        for key in (
            "metric_source_pass",
            "all_cases_converged",
            "plasticity_triggered_all_cases",
            "collapse_path_pass",
            "min_plastic_story_count_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"pushover_stress.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("pushover_stress.summary missing")
    else:
        for key in (
            "case_count",
            "peak_plastic_story_count_min",
            "peak_plastic_story_count_mean",
            "drift_amplification_min",
            "drift_amplification_mean",
        ):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"pushover_stress.summary.{key} invalid")
        fy_mean = summary.get("first_yield_load_factor_mean")
        if fy_mean is not None and not _is_finite_number(fy_mean):
            errs.append("pushover_stress.summary.first_yield_load_factor_mean invalid")
        if not isinstance(summary.get("load_factors"), list):
            errs.append("pushover_stress.summary.load_factors invalid")
    if not isinstance(report.get("rows"), list):
        errs.append("pushover_stress.rows invalid")
    return errs


def validate_ndtha_stress(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "ndtha_stress"))
    if report.get("reason_code") not in ALLOWED_NDTHA_STRESS_REASON:
        errs.append("ndtha_stress.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("ndtha_stress.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("ndtha_stress.checks missing")
    else:
        for key in (
            "metric_source_pass",
            "pdelta_enabled_pass",
            "dynamic_reversal_pass",
            "rayleigh_damping_pass",
            "collapse_cutoff_guard_pass",
            "no_collapse_detected",
            "all_cases_converged",
            "rust_backend_used_pass",
            "plasticity_triggered_all_cases",
            "min_plastic_story_count_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"ndtha_stress.checks.{key} invalid")
    gm = report.get("ground_motion")
    if not isinstance(gm, dict):
        errs.append("ndtha_stress.ground_motion missing")
    else:
        for key in ("step_count", "dt_s", "max_abs_accel_g", "reversal_count"):
            if not _is_finite_number(gm.get(key)):
                errs.append(f"ndtha_stress.ground_motion.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("ndtha_stress.summary missing")
    else:
        for key in (
            "case_count",
            "peak_plastic_story_count_min",
            "peak_plastic_story_count_mean",
            "max_drift_ratio_pct_max",
            "avg_step_iterations_mean",
        ):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"ndtha_stress.summary.{key} invalid")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("ndtha_stress.artifacts missing")
    else:
        for key in ("report_json", "response_npz_out"):
            val = artifacts.get(key)
            if not isinstance(val, str):
                errs.append(f"ndtha_stress.artifacts.{key} invalid")
                continue
            if not Path(val).exists():
                errs.append(f"ndtha_stress.artifacts.{key} missing")
    if not isinstance(report.get("rows"), list):
        errs.append("ndtha_stress.rows invalid")
    return errs


def validate_ndtha_residual_gate(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "ndtha_residual_gate"))
    if report.get("reason_code") not in ALLOWED_NDTHA_RESIDUAL_GATE_REASON:
        errs.append("ndtha_residual_gate.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("ndtha_residual_gate.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("ndtha_residual_gate.checks missing")
    else:
        for key in (
            "case_count_pass",
            "ndtha_contract_pass",
            "ndtha_no_collapse_pass",
            "summary_residual_finite_pass",
            "residual_metric_trace_pass",
            "residual_top_hard_pass",
            "residual_drift_hard_pass",
            "fallback_rate_pass",
            "recommended_top_pass",
            "recommended_drift_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"ndtha_residual_gate.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("ndtha_residual_gate.summary missing")
    else:
        for key in (
            "case_count",
            "residual_top_displacement_m_max_abs",
            "residual_drift_ratio_pct_max_abs",
            "raw_residual_top_displacement_m_max_abs",
            "raw_residual_drift_ratio_pct_max_abs",
            "fallback_case_count",
            "fallback_rate",
        ):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"ndtha_residual_gate.summary.{key} invalid")
        for key in (
            "fallback_case_ids",
            "recommended_top_exceed_case_ids",
            "recommended_drift_exceed_case_ids",
        ):
            if not isinstance(summary.get(key), list):
                errs.append(f"ndtha_residual_gate.summary.{key} invalid")
        if not isinstance(summary.get("residual_metric_source_counts"), dict):
            errs.append("ndtha_residual_gate.summary.residual_metric_source_counts invalid")
    if not isinstance(report.get("rows"), list):
        errs.append("ndtha_residual_gate.rows invalid")
    return errs


def validate_pbd_review(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "pbd_review"))
    if report.get("reason_code") not in ALLOWED_PBD_REVIEW_REASON:
        errs.append("pbd_review.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("pbd_review.contract_pass invalid")

    inputs = report.get("inputs")
    if not isinstance(inputs, dict):
        errs.append("pbd_review.inputs missing")
    else:
        for key in ("earthquake_count", "commercial_estimate_hours", "cp_lower_pct", "cp_upper_pct"):
            if not _is_finite_number(inputs.get(key)):
                errs.append(f"pbd_review.inputs.{key} invalid")

    selected_case_ids = report.get("selected_case_ids")
    if not isinstance(selected_case_ids, list):
        errs.append("pbd_review.selected_case_ids invalid")
    elif len(selected_case_ids) < 7:
        errs.append("pbd_review.selected_case_ids too short")

    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("pbd_review.artifacts missing")
    else:
        for key in (
            "drift_envelope_png",
            "core_hysteresis_png",
            "killshot_metrics_json",
            "killshot_metrics_csv",
            "killshot_metrics_npz",
            "review_markdown",
            "review_pdf",
        ):
            val = artifacts.get(key)
            if not isinstance(val, str):
                errs.append(f"pbd_review.artifacts.{key} invalid")
                continue
            if not Path(val).exists():
                errs.append(f"pbd_review.artifacts.{key} missing")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("pbd_review.summary missing")
    else:
        if not isinstance(summary.get("response_storage"), str):
            errs.append("pbd_review.summary.response_storage invalid")
        if not _is_finite_number(summary.get("case_metrics_npz_case_count")):
            errs.append("pbd_review.summary.case_metrics_npz_case_count invalid")

    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("pbd_review.metrics missing")
    else:
        for key in (
            "earthquake_case_count",
            "engine_wall_time_minutes",
            "commercial_estimate_hours",
            "speedup_vs_estimate",
            "drift_envelope_max_pct",
            "residual_top_displacement_mm_max_abs",
            "residual_drift_pct_max_abs",
            "converged_step_ratio_min",
            "energy_balance_relative_error_ref",
            "equilibrium_residual_ratio_ref",
        ):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"pbd_review.metrics.{key} invalid")
        for key in ("all_cases_converged",):
            if not isinstance(metrics.get(key), bool):
                errs.append(f"pbd_review.metrics.{key} invalid")
        try:
            eq_count = int(metrics.get("earthquake_case_count", 0) or 0)
        except Exception:
            eq_count = 0
        if eq_count < 7:
            errs.append("pbd_review.metrics.earthquake_case_count too small")

    return errs


def validate_global_authority_gate(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "global_authority"))
    if report.get("reason_code") not in ALLOWED_GLOBAL_AUTHORITY_REASON:
        errs.append("global_authority.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("global_authority.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("global_authority.checks missing")
    else:
        for key in (
            "opensees_pass",
            "sac_pass",
            "nheri_pass",
            "holdout_manifest_pass",
            "sac_min_case_count_pass",
            "nheri_min_case_count_pass",
            "opensees_required",
            "sac_required",
            "nheri_required",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"global_authority.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("global_authority.summary missing")
    else:
        for key in (
            "opensees_case_count",
            "opensees_contract_pass_count",
            "sac_case_count",
            "sac_valid_count",
            "nheri_case_count",
            "nheri_valid_count",
            "case_metrics_npz_case_count",
            "case_metrics_npz_step_count",
        ):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"global_authority.summary.{key} invalid")
        if not isinstance(summary.get("response_storage"), str):
            errs.append("global_authority.summary.response_storage invalid")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("global_authority.artifacts missing")
    else:
        for key in ("report_json", "case_metrics_npz_out"):
            val = artifacts.get(key)
            if not isinstance(val, str):
                errs.append(f"global_authority.artifacts.{key} invalid")
            elif not Path(val).exists():
                errs.append(f"global_authority.artifacts.{key} missing")
    if not isinstance(report.get("steps"), list):
        errs.append("global_authority.steps invalid")
    return errs


def validate_wind_benchmark(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "wind_benchmark"))
    if report.get("reason_code") not in ALLOWED_WIND_BENCHMARK_REASON:
        errs.append("wind_benchmark.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("wind_benchmark.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("wind_benchmark.checks missing")
    else:
        for key in (
            "source_manifest_pass",
            "wind_duration_pass",
            "wind_reversal_pass",
            "case_count_pass",
            "long_series_chunked_pass",
            "all_cases_converged",
            "rust_backend_used_pass",
            "no_collapse_detected",
            "drift_guard_pass",
            "section_family_pass",
            "material_model_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"wind_benchmark.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("wind_benchmark.summary missing")
    else:
        for key in ("duration_hours", "time_step_s", "effective_time_step_s", "load_reversal_count", "total_chunk_count", "section_family_coverage_min"):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"wind_benchmark.summary.{key} invalid")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("wind_benchmark.artifacts missing")
    else:
        for key in ("report_json", "case_metrics_npz_out"):
            val = artifacts.get(key)
            if not isinstance(val, str):
                errs.append(f"wind_benchmark.artifacts.{key} invalid")
                continue
            if not Path(val).exists():
                errs.append(f"wind_benchmark.artifacts.{key} missing")
    if not isinstance(report.get("rows"), list):
        errs.append("wind_benchmark.rows invalid")
    return errs


def validate_ssi_boundary(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "ssi_boundary"))
    if report.get("reason_code") not in ALLOWED_SSI_BOUNDARY_REASON:
        errs.append("ssi_boundary.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("ssi_boundary.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("ssi_boundary.checks missing")
    else:
        for key in (
            "case_count_pass",
            "ssi_nonlinear_boundary_active",
            "ssi_transfer_finite",
            "all_cases_converged",
            "rust_backend_used_pass",
            "no_collapse_detected",
            "shear_delta_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"ssi_boundary.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("ssi_boundary.summary missing")
    else:
        for key in ("dominant_frequency_hz", "nonlinear_ratio_min", "nonlinear_ratio_max", "nonlinear_ratio_span"):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"ssi_boundary.summary.{key} invalid")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("ssi_boundary.artifacts missing")
    else:
        for key in ("report_json", "case_metrics_npz_out"):
            val = artifacts.get(key)
            if not isinstance(val, str):
                errs.append(f"ssi_boundary.artifacts.{key} invalid")
                continue
            if not Path(val).exists():
                errs.append(f"ssi_boundary.artifacts.{key} missing")
    if not isinstance(report.get("rows"), list):
        errs.append("ssi_boundary.rows invalid")
    return errs


def validate_damper_validation(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "damper_validation"))
    if report.get("reason_code") not in ALLOWED_DAMPER_VALIDATION_REASON:
        errs.append("damper_validation.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("damper_validation.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("damper_validation.checks missing")
    else:
        for key in (
            "case_count_pass",
            "source_integrity_pass",
            "damper_type_diversity_pass",
            "waveform_corr_pass",
            "phase_error_pass",
            "residual_drift_pass",
            "damping_reduction_pass",
            "section_family_pass",
            "material_model_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"damper_validation.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("damper_validation.summary missing")
    else:
        for key in ("case_count", "waveform_corr_min", "phase_error_ms_max", "residual_drift_mm_max", "section_family_coverage_min"):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"damper_validation.summary.{key} invalid")
    if not isinstance(report.get("rows"), list):
        errs.append("damper_validation.rows invalid")
    return errs


def validate_kds_compliance(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "kds_compliance"))
    if report.get("reason_code") not in ALLOWED_KDS_COMPLIANCE_REASON:
        errs.append("kds_compliance.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("kds_compliance.contract_pass invalid")
    if not isinstance(report.get("rows"), list):
        errs.append("kds_compliance.rows invalid")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict):
        errs.append("kds_compliance.artifacts missing")
    else:
        for key in (
            "kds_compliance_csv",
            "kds_compliance_markdown",
            "kds_compliance_pdf",
            "kds_frontend_payload_json",
        ):
            val = artifacts.get(key)
            if not isinstance(val, str):
                errs.append(f"kds_compliance.artifacts.{key} invalid")
            elif not Path(val).exists():
                errs.append(f"kds_compliance.artifacts.{key} missing")
    frontend = report.get("frontend_payload")
    if not isinstance(frontend, dict):
        errs.append("kds_compliance.frontend_payload missing")
    else:
        if not isinstance(frontend.get("summary_cards"), list):
            errs.append("kds_compliance.frontend_payload.summary_cards invalid")
        if not isinstance(frontend.get("compliance_rows"), list):
            errs.append("kds_compliance.frontend_payload.compliance_rows invalid")
        if not isinstance(frontend.get("governing_members_top50"), list):
            errs.append("kds_compliance.frontend_payload.governing_members_top50 invalid")
        if not isinstance(frontend.get("governing_combo_rows_top150"), list):
            errs.append("kds_compliance.frontend_payload.governing_combo_rows_top150 invalid")
        if not isinstance(frontend.get("governing_member_checks_top500"), list):
            errs.append("kds_compliance.frontend_payload.governing_member_checks_top500 invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("kds_compliance.summary missing")
    else:
        for key in (
            "status_item_count",
            "pass_item_count",
            "fail_item_count",
            "summary_card_count",
            "compliance_row_count",
            "member_check_row_count",
            "combination_row_count",
            "clause_count",
            "member_type_count",
        ):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"kds_compliance.summary.{key} invalid")
    return errs


def validate_construction_sequence(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "construction_sequence"))
    if report.get("reason_code") not in ALLOWED_CONSTRUCTION_SEQUENCE_REASON:
        errs.append("construction_sequence.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("construction_sequence.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("construction_sequence.checks missing")
    else:
        for key in (
            "case_count_pass",
            "all_stages_converged",
            "rust_backend_used_pass",
            "stagewise_monotonic_load_pass",
            "creep_shrinkage_applied",
            "differential_shortening_detected",
            "initial_stress_nonzero",
            "initial_stress_upper_bound_pass",
            "drift_guard_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"construction_sequence.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("construction_sequence.summary missing")
    else:
        for key in (
            "case_count",
            "stage_count",
            "construction_years",
            "max_stage_drift_pct_all_cases",
            "max_differential_shortening_mm",
            "max_initial_stress_mpa",
            "mean_initial_stress_mpa",
        ):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"construction_sequence.summary.{key} invalid")
    if not isinstance(report.get("rows"), list):
        errs.append("construction_sequence.rows invalid")
    return errs


def validate_flexible_diaphragm(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "flexible_diaphragm"))
    if report.get("reason_code") not in ALLOWED_FLEXIBLE_DIAPHRAGM_REASON:
        errs.append("flexible_diaphragm.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("flexible_diaphragm.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("flexible_diaphragm.checks missing")
    else:
        for key in (
            "case_count_pass",
            "shell_beam_mix_topology_pass",
            "flexible_diaphragm_modeled",
            "all_cases_converged",
            "rust_backend_used_pass",
            "flex_amplification_band_pass",
            "slab_shear_stress_pass",
            "max_flexible_drift_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"flexible_diaphragm.checks.{key} invalid")
    topo = report.get("topology_scan")
    if not isinstance(topo, dict):
        errs.append("flexible_diaphragm.topology_scan missing")
    else:
        for key in ("has_shell", "has_beam", "shell_beam_mix", "rigid_diaphragm_declared"):
            if not isinstance(topo.get(key), bool):
                errs.append(f"flexible_diaphragm.topology_scan.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("flexible_diaphragm.summary missing")
    else:
        for key in (
            "case_count",
            "flex_amplification_min",
            "flex_amplification_max",
            "slab_shear_stress_mpa_max",
            "max_flexible_drift_pct",
        ):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"flexible_diaphragm.summary.{key} invalid")
    if not isinstance(report.get("rows"), list):
        errs.append("flexible_diaphragm.rows invalid")
    return errs


def validate_repro_version_lock(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "repro_version_lock"))
    if report.get("reason_code") not in ALLOWED_REPRO_VERSION_LOCK_REASON:
        errs.append("repro_version_lock.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("repro_version_lock.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("repro_version_lock.checks missing")
    else:
        for key in (
            "case_count_pass",
            "seed_locked",
            "input_hashes_frozen",
            "model_hashes_frozen",
            "no_missing_model_artifacts",
            "rust_backend_used_pass",
            "replay_exact_match",
            "lock_manifest_written",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"repro_version_lock.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("repro_version_lock.summary missing")
    else:
        for key in ("case_count", "replay_runs", "seed"):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"repro_version_lock.summary.{key} invalid")
        if not isinstance(summary.get("replay_hashes"), list):
            errs.append("repro_version_lock.summary.replay_hashes invalid")
        if not isinstance(summary.get("missing_model_artifacts"), list):
            errs.append("repro_version_lock.summary.missing_model_artifacts invalid")
    lock_manifest = report.get("lock_manifest")
    if not isinstance(lock_manifest, str):
        errs.append("repro_version_lock.lock_manifest invalid")
    elif lock_manifest and not Path(lock_manifest).exists():
        errs.append("repro_version_lock.lock_manifest missing")
    rows_head = report.get("rows_head")
    if not isinstance(rows_head, list):
        errs.append("repro_version_lock.rows_head invalid")
    return errs


def validate_release_registry(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "release_registry"))
    if report.get("reason_code") not in ALLOWED_RELEASE_REGISTRY_REASON:
        errs.append("release_registry.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("release_registry.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("release_registry.checks missing")
    else:
        for key in (
            "green_reports_pass",
            "lock_manifest_hash_match",
            "artifact_hashes_present_pass",
            "public_key_written_pass",
            "signature_generated_pass",
            "signature_verified_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"release_registry.checks.{key} invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("release_registry.summary missing")
    else:
        for key in ("artifact_count", "model_hash_count", "input_hash_count"):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"release_registry.summary.{key} invalid")
        if not isinstance(summary.get("key_generated_this_run"), bool):
            errs.append("release_registry.summary.key_generated_this_run invalid")
        if str(summary.get("signing_algorithm", "")).lower() != "ed25519":
            errs.append("release_registry.summary.signing_algorithm invalid")
        if not isinstance(summary.get("registry_body_sha256"), str):
            errs.append("release_registry.summary.registry_body_sha256 invalid")
    registry_body = report.get("registry_body")
    if not isinstance(registry_body, dict):
        errs.append("release_registry.registry_body missing")
    else:
        for key in ("input_hashes", "model_hashes", "provenance", "parser_provenance", "package_provenance"):
            if not isinstance(registry_body.get(key), dict):
                errs.append(f"release_registry.registry_body.{key} invalid")
        if not isinstance(registry_body.get("artifacts"), list):
            errs.append("release_registry.registry_body.artifacts invalid")
    signature = report.get("signature")
    if not isinstance(signature, dict):
        errs.append("release_registry.signature missing")
    else:
        if str(signature.get("algorithm", "")).lower() != "ed25519":
            errs.append("release_registry.signature.algorithm invalid")
        for key in ("public_key_path", "signature_b64", "signature_out", "canonical_body_sha256"):
            val = signature.get(key)
            if not isinstance(val, str) or not val:
                errs.append(f"release_registry.signature.{key} invalid")
    return errs


def validate_topology_gate(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "topology_gate"))
    if report.get("reason_code") not in ALLOWED_TOPOLOGY_GATE_REASON:
        errs.append("topology_gate.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("topology_gate.contract_pass invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("topology_gate.checks missing")
    else:
        for key in (
            "source_is_opensees_text",
            "source_manifest_pass",
            "synthetic_source_detected",
            "min_nodes_pass",
            "edge_node_ratio_pass",
            "degree_entropy_pass",
            "element_type_count_pass",
            "largest_component_pass",
            "shell_beam_mix_pass",
            "real_topology_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"topology_gate.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("topology_gate.metrics missing")
    else:
        for key in (
            "node_count",
            "edge_count_undirected",
            "edge_node_ratio",
            "degree_entropy",
            "largest_component_ratio",
            "mean_degree",
            "max_degree",
            "element_type_count",
            "shell_element_count",
            "beam_element_count",
        ):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"topology_gate.metrics.{key} invalid")
        if not isinstance(metrics.get("element_type_histogram"), dict):
            errs.append("topology_gate.metrics.element_type_histogram invalid")
        if not isinstance(metrics.get("element_class_histogram"), dict):
            errs.append("topology_gate.metrics.element_class_histogram invalid")

    if not isinstance(report.get("source_provenance"), dict):
        errs.append("topology_gate.source_provenance invalid")
    if not isinstance(report.get("parse_counters"), dict):
        errs.append("topology_gate.parse_counters invalid")
    if not isinstance(report.get("artifacts"), dict):
        errs.append("topology_gate.artifacts invalid")
    return errs


def validate_sync_stress(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "sync_stress"))
    if report.get("reason_code") not in ALLOWED_SYNC_STRESS_REASON:
        errs.append("sync_stress.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("sync_stress.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("sync_stress.checks missing")
    else:
        for key in ("topology_gate_pass", "required_levels_present", "required_levels_sync_pass", "sync_stall_budget_pass", "backend_policy_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"sync_stress.checks.{key} invalid")
        for key in ("virtual_sync_blocked_pass", "feti_profile_pass", "inline_native_smoke_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"sync_stress.checks.{key} invalid")
    if not isinstance(report.get("level_rows"), list):
        errs.append("sync_stress.level_rows invalid")
    else:
        for i, row in enumerate(report.get("level_rows", [])):
            if not isinstance(row, dict):
                errs.append(f"sync_stress.level_rows[{i}] invalid")
                continue
            for key in ("node_count", "contract_pass", "reason_code", "backend", "sync_stall_ratio", "p99_step_ms", "straggler_ratio", "comm_overlap_ratio"):
                if key not in row:
                    errs.append(f"sync_stress.level_rows[{i}].{key} missing")
    if not isinstance(report.get("steps"), list):
        errs.append("sync_stress.steps invalid")
    return errs


def validate_phasea(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasea"))
    if report.get("reason_code") not in ALLOWED_PHASEA_REASON:
        errs.append("phasea.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasea.contract_pass invalid")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phasea.checks missing")
    else:
        for key in (
            "dynamics_domain_reports_pass",
            "vehicle_schema_pass",
            "tunnel_schema_pass",
            "soil_impedance_table_pass",
            "material_rule_table_pass",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phasea.checks.{key} invalid")

    errs_obj = report.get("errors")
    if not isinstance(errs_obj, dict):
        errs.append("phasea.errors missing")
    else:
        for key in (
            "io",
            "dynamics_domain_reports",
            "vehicle_schema",
            "tunnel_schema",
            "soil_impedance_table",
            "material_rule_table",
        ):
            if not isinstance(errs_obj.get(key), list):
                errs.append(f"phasea.errors.{key} invalid")
    return errs


def validate_track_lf(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "track_lf"))
    if report.get("reason_code") not in ALLOWED_TRACK_LF_REASON:
        errs.append("track_lf.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("track_lf.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("track_lf.checks missing")
    else:
        for key in ("all_converged", "accuracy_pass", "o_n_operator", "matrix_free_euler"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"track_lf.checks.{key} invalid")
    return errs


def validate_moving_load(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "moving_load"))
    if report.get("reason_code") not in ALLOWED_MOVING_LOAD_REASON:
        errs.append("moving_load.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("moving_load.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("moving_load.checks missing")
    else:
        for key in ("finite_response", "non_divergent_response", "linear_solver_converged", "equilibrium_residual_pass", "energy_balance_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"moving_load.checks.{key} invalid")
    return errs


def validate_vti(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "vti"))
    if report.get("reason_code") not in ALLOWED_VTI_REASON:
        errs.append("vti.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("vti.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("vti.checks missing")
    else:
        for key in ("finite_response", "coupling_converged_ratio_pass", "dynamic_disp_pass", "adaptive_newton_converged_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"vti.checks.{key} invalid")
    return errs


def validate_irregularity(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "irregularity"))
    if report.get("reason_code") not in ALLOWED_IRREGULARITY_REASON:
        errs.append("irregularity.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("irregularity.contract_pass invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("irregularity.metrics missing")
    else:
        for key in ("node_count", "dx_m", "length_m", "rms_m", "peak_abs_m"):
            if key not in metrics:
                errs.append(f"irregularity.metrics.{key} missing")
    return errs


def validate_phaseb_summary(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phaseb_summary"))
    if report.get("reason_code") not in ALLOWED_PHASEB_SUMMARY_REASON:
        errs.append("phaseb_summary.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phaseb_summary.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phaseb_summary.checks missing")
    else:
        for key in (
            "B1_track_lf_solver",
            "B2_moving_load_integrator",
            "B3_vti_coupled_solver",
            "B4_track_irregularity_generator",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phaseb_summary.checks.{key} invalid")
    return errs


def validate_phased_track_dataset(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phased_track_dataset"))
    if report.get("reason_code") not in ALLOWED_PHASED_TRACK_DATASET_REASON:
        errs.append("phased_track_dataset.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phased_track_dataset.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phased_track_dataset.checks missing")
    else:
        for key in ("dataset_nonempty", "split_has_val_test", "finite_response", "equilibrium_residual_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phased_track_dataset.checks.{key} invalid")
    outputs = report.get("outputs")
    if not isinstance(outputs, dict):
        errs.append("phased_track_dataset.outputs missing")
    else:
        if not isinstance(outputs.get("dataset_path"), str):
            errs.append("phased_track_dataset.outputs.dataset_path invalid")
        if not isinstance(outputs.get("case_count"), int):
            errs.append("phased_track_dataset.outputs.case_count invalid")
    return errs


def validate_phased_tunnel_dataset(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phased_tunnel_dataset"))
    if report.get("reason_code") not in ALLOWED_PHASED_TUNNEL_DATASET_REASON:
        errs.append("phased_tunnel_dataset.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phased_tunnel_dataset.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phased_tunnel_dataset.checks missing")
    else:
        for key in ("dataset_nonempty", "split_has_val_test", "finite_response", "equilibrium_residual_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phased_tunnel_dataset.checks.{key} invalid")
    outputs = report.get("outputs")
    if not isinstance(outputs, dict):
        errs.append("phased_tunnel_dataset.outputs missing")
    else:
        if not isinstance(outputs.get("dataset_path"), str):
            errs.append("phased_tunnel_dataset.outputs.dataset_path invalid")
        if not isinstance(outputs.get("case_count"), int):
            errs.append("phased_tunnel_dataset.outputs.case_count invalid")
    return errs


def validate_phased_attention(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phased_attention"))
    if report.get("reason_code") not in ALLOWED_PHASED_ATTENTION_REASON:
        errs.append("phased_attention.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phased_attention.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phased_attention.checks missing")
    else:
        for key in ("peak_centered", "bounded_nonnegative", "shape_monotonic", "speed_scaling_monotonic"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phased_attention.checks.{key} invalid")
    return errs


def validate_phased_tgnn(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phased_tgnn"))
    if report.get("reason_code") not in ALLOWED_PHASED_TGNN_REASON:
        errs.append("phased_tgnn.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phased_tgnn.contract_pass invalid")
    domain_checks = report.get("domain_checks")
    if not isinstance(domain_checks, dict):
        errs.append("phased_tgnn.domain_checks missing")
    else:
        for key in ("overall_val_gate_pass", "track_val_gate_pass", "tunnel_val_gate_pass"):
            if not isinstance(domain_checks.get(key), bool):
                errs.append(f"phased_tgnn.domain_checks.{key} invalid")
    domain_counts = report.get("domain_case_counts")
    if not isinstance(domain_counts, dict):
        errs.append("phased_tgnn.domain_case_counts missing")
    return errs


def validate_phased_summary(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phased_summary"))
    if report.get("reason_code") not in ALLOWED_PHASED_SUMMARY_REASON:
        errs.append("phased_summary.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phased_summary.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phased_summary.checks missing")
    else:
        for key in (
            "D1_generate_track_dynamics_dataset",
            "D2_generate_tunnel_dynamics_dataset",
            "D3_train_tgnn_multidomain",
            "D4_moving_load_attention",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phased_summary.checks.{key} invalid")
    return errs


def validate_phasee_substructuring(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasee_substructuring"))
    if report.get("reason_code") not in ALLOWED_PHASEE_SUBSTRUCTURING_REASON:
        errs.append("phasee_substructuring.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasee_substructuring.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phasee_substructuring.checks missing")
    else:
        for key in ("interface_dof_match", "finite_transfer", "monotonic_path_attenuation", "coupling_stability"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phasee_substructuring.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("phasee_substructuring.metrics missing")
    else:
        for key in ("max_condition_number", "max_track_disp_m", "max_building_disp_m", "mean_transfer_ratio_building_to_track"):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"phasee_substructuring.metrics.{key} invalid")
    curve_head = report.get("curve_head")
    if not isinstance(curve_head, list):
        errs.append("phasee_substructuring.curve_head invalid")
    return errs


def validate_phasee_attenuation(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasee_attenuation"))
    if report.get("reason_code") not in ALLOWED_PHASEE_ATTENUATION_REASON:
        errs.append("phasee_attenuation.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasee_attenuation.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phasee_attenuation.checks missing")
    else:
        for key in ("substructuring_linked", "finite_values", "monotonic_distance_decay", "high_frequency_decay_stronger"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phasee_attenuation.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("phasee_attenuation.metrics missing")
    else:
        for key in ("distance_count", "max_velocity_mm_s", "min_velocity_mm_s", "far_field_ratio_63_to_8"):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"phasee_attenuation.metrics.{key} invalid")
    curve_head = report.get("curve_head")
    if not isinstance(curve_head, list):
        errs.append("phasee_attenuation.curve_head invalid")
    return errs


def validate_phasee_compliance(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasee_compliance"))
    if report.get("reason_code") not in ALLOWED_PHASEE_COMPLIANCE_REASON:
        errs.append("phasee_compliance.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasee_compliance.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phasee_compliance.checks missing")
    else:
        for key in ("standard_supported", "finite_values", "compliance_ratio_pass"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phasee_compliance.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("phasee_compliance.metrics missing")
    else:
        for key in ("sample_count", "pass_ratio", "max_velocity_mm_s", "max_over_limit_ratio", "max_vibration_db"):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"phasee_compliance.metrics.{key} invalid")
    curve_head = report.get("curve_head")
    if not isinstance(curve_head, list):
        errs.append("phasee_compliance.curve_head invalid")
    return errs


def validate_phasee_whitebox(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasee_whitebox"))
    if report.get("reason_code") not in ALLOWED_PHASEE_WHITEBOX_REASON:
        errs.append("phasee_whitebox.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasee_whitebox.contract_pass invalid")
    if not isinstance(report.get("cases"), list):
        errs.append("phasee_whitebox.cases invalid")
    if not isinstance(report.get("domains"), list):
        errs.append("phasee_whitebox.domains invalid")
    rows = report.get("rows")
    if not isinstance(rows, list):
        errs.append("phasee_whitebox.rows invalid")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errs.append("phasee_whitebox.summary invalid")
    else:
        for key in (
            "max_lf_rel_err",
            "max_gnn_rel_err",
            "max_gnn_non_residual_err",
            "max_gnn_residual_abs",
            "improved_ratio",
            "acceptance_rel_err",
            "acceptance_abs_residual",
            "min_improved_ratio",
        ):
            if not _is_finite_number(summary.get(key)):
                errs.append(f"phasee_whitebox.summary.{key} invalid")
        if not isinstance(summary.get("pass"), bool):
            errs.append("phasee_whitebox.summary.pass invalid")
    if not isinstance(report.get("domain_summary"), dict):
        errs.append("phasee_whitebox.domain_summary invalid")
    return errs


def validate_phasee_summary(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasee_summary"))
    if report.get("reason_code") not in ALLOWED_PHASEE_SUMMARY_REASON:
        errs.append("phasee_summary.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasee_summary.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phasee_summary.checks missing")
    else:
        for key in (
            "E1_substructuring_interface",
            "E2_vibration_attenuation_model",
            "E3_vibration_compliance_checker",
            "E5_whitebox_validation_extension",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phasee_summary.checks.{key} invalid")
    if not isinstance(report.get("reports"), dict):
        errs.append("phasee_summary.reports invalid")
    if not isinstance(report.get("steps"), list):
        errs.append("phasee_summary.steps invalid")
    return errs


def validate_phasef_l3(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasef_l3"))
    if report.get("reason_code") not in ALLOWED_PHASEF_L3_REASON:
        errs.append("phasef_l3.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasef_l3.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phasef_l3.checks missing")
    else:
        for key in ("high_frequency_target", "windowed_o_n_streaming", "near_field_refined", "has_cache_safe_chunk"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phasef_l3.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("phasef_l3.metrics missing")
    else:
        for key in (
            "refinement_factor",
            "active_nodes_window",
            "active_node_ratio",
            "cache_safe_chunk_count",
            "max_cache_safe_chunk",
            "recommended_chunk",
            "recommended_working_set_mb",
        ):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"phasef_l3.metrics.{key} invalid")
    if not isinstance(report.get("scenarios"), list):
        errs.append("phasef_l3.scenarios invalid")
    return errs


def validate_phasef_phase(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasef_phase"))
    if report.get("reason_code") not in ALLOWED_PHASEF_PHASE_REASON:
        errs.append("phasef_phase.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasef_phase.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phasef_phase.checks missing")
    else:
        for key in ("phase_error_improved", "phase_error_below_threshold", "time_lag_below_threshold", "amplitude_error_not_degraded"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phasef_phase.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("phasef_phase.metrics missing")
    else:
        for key in (
            "pre_phase_error_deg",
            "post_phase_error_deg",
            "pre_time_lag_ms",
            "post_time_lag_ms",
            "pre_mae_pct",
            "post_mae_pct",
            "phase_error_reduction_ratio",
        ):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"phasef_phase.metrics.{key} invalid")
    if not isinstance(report.get("trajectory_head"), list):
        errs.append("phasef_phase.trajectory_head invalid")
    return errs


def validate_phasef_soil_ood(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasef_soil_ood"))
    if report.get("reason_code") not in ALLOWED_PHASEF_SOIL_OOD_REASON:
        errs.append("phasef_soil_ood.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasef_soil_ood.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phasef_soil_ood.checks missing")
    else:
        for key in ("ood_recall_pass", "false_negative_gate_pass", "fallback_route_on_ood_pass", "uncertainty_calibrated"):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phasef_soil_ood.checks.{key} invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        errs.append("phasef_soil_ood.metrics missing")
    else:
        for key in (
            "tp",
            "fn",
            "fp",
            "tn",
            "recall",
            "false_negative_ratio",
            "false_positive_rate",
            "md_uncertainty_corr",
            "fallback_ratio_on_ood",
        ):
            if not _is_finite_number(metrics.get(key)):
                errs.append(f"phasef_soil_ood.metrics.{key} invalid")
    if not isinstance(report.get("samples_head"), list):
        errs.append("phasef_soil_ood.samples_head invalid")
    return errs


def validate_phasef_summary(report: dict) -> list[str]:
    errs: list[str] = []
    errs.extend(_validate_common_metadata(report, "phasef_summary"))
    if report.get("reason_code") not in ALLOWED_PHASEF_SUMMARY_REASON:
        errs.append("phasef_summary.reason_code invalid")
    if not isinstance(report.get("contract_pass"), bool):
        errs.append("phasef_summary.contract_pass invalid")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errs.append("phasef_summary.checks missing")
    else:
        for key in (
            "F1_multiscale_l3_streaming",
            "F2_phase_correction_assimilation",
            "F3_heterogeneous_soil_ood_gate",
        ):
            if not isinstance(checks.get(key), bool):
                errs.append(f"phasef_summary.checks.{key} invalid")
    if not isinstance(report.get("reports"), dict):
        errs.append("phasef_summary.reports invalid")
    if not isinstance(report.get("steps"), list):
        errs.append("phasef_summary.steps invalid")
    return errs

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", default="implementation/phase1/lf_to_gnn_e2e_smoke_report.json")
    p.add_argument("--ci", default="implementation/phase1/ci_gate_report.json")
    p.add_argument("--rca", default="implementation/phase1/step_outputs/step5_rca_summary.json")
    p.add_argument("--priority", default="implementation/phase1/priority3_summary.json")
    p.add_argument("--dyn", default="implementation/phase1/dynamics_boundary_report.json")
    p.add_argument("--pgat", default="implementation/phase1/pg_gat_contract_report.json")
    p.add_argument("--subproj", default="implementation/phase1/subgraph_projection_report.json")
    p.add_argument("--soa", default="implementation/phase1/soa_dlpack_contract_report.json")
    p.add_argument("--physics-residual", default="implementation/phase1/physics_residual_contract_report.json")
    p.add_argument("--meta-learning", default="implementation/phase1/meta_learning_task_report.json")
    p.add_argument("--buckling", default="implementation/phase1/buckling_contract_report.json")
    p.add_argument("--benchmark", default="implementation/phase1/hf_benchmark_report.json")
    p.add_argument("--branching", default="implementation/phase1/physics_branching_report.json")
    p.add_argument("--bifurcation", default="implementation/phase1/bifurcation_detector_report.json")
    p.add_argument("--rust-onnx", default="implementation/phase1/rust_onnx_native_contract_report.json")
    p.add_argument("--winning-ticket", default="implementation/phase1/winning_ticket_backprop_report.json")
    p.add_argument("--rust-parity", default="implementation/phase1/rust_md3bead_parity_report.json")
    p.add_argument("--lj-mapping", default="implementation/phase1/nonlinear_lj_mapping_report.json")
    p.add_argument("--dynamic-time-history", default="implementation/phase1/dynamic_time_history_report.json")
    p.add_argument("--cache-profile", default="implementation/phase1/branch64_microbatch_profile_report.json")
    p.add_argument("--p0-engine-perf", default="implementation/phase1/p0_engine_perf_report.json")
    p.add_argument("--p0-core-gap", default="implementation/phase1/p0_core_gap_report.json")
    p.add_argument("--hip-kernel-smoke", default="implementation/phase1/hip_kernel_smoke_report.json")
    p.add_argument("--noise-stress", default="implementation/phase1/noise_sensitivity_stress_report.json")
    p.add_argument("--scaleout-io", default="implementation/phase1/scaleout_io_profile_report.json")
    p.add_argument("--nightly-10m-repro", default="implementation/phase1/nightly_10m_repro_report.json")
    p.add_argument("--ndtha-long-profile", default="implementation/phase1/ndtha_long_profile_report.json")
    p.add_argument("--phase3-pipeline", default="implementation/phase1/phase3_megastructure_pipeline_report.json")
    p.add_argument("--topology-gate", default="implementation/phase1/opensees_topology_report.json")
    p.add_argument("--partitioned-scaleout", default="implementation/phase1/partitioned_scaleout_report.json")
    p.add_argument("--sync-stress", default="implementation/phase1/sync_stress_gate_report.json")
    p.add_argument("--noise-convergence", default="implementation/phase1/noise_convergence_gate_report.json")
    p.add_argument("--commercial-csv-gate", default="implementation/phase1/commercial_csv_gate_report.json")
    p.add_argument("--midas-mgt-conversion", default="implementation/phase1/midas_mgt_conversion_report.json")
    p.add_argument("--commercial-readiness", default="implementation/phase1/commercial_readiness_report.json")
    p.add_argument("--real-source-multi", default="implementation/phase1/real_source_multi_gate_report.json")
    p.add_argument("--nonlinear-engine", default="implementation/phase1/nonlinear_frame_engine_report.json")
    p.add_argument("--pushover-stress", default="implementation/phase1/nonlinear_pushover_stress_report.json")
    p.add_argument("--ndtha-stress", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    p.add_argument("--ndtha-residual-gate", default="implementation/phase1/ndtha_residual_gate_report.json")
    p.add_argument("--pbd-review-package", default="implementation/phase1/release/pbd_review/pbd_review_package_report.json")
    p.add_argument("--global-authority-gate", default="implementation/phase1/global_authority_gate_report.json")
    p.add_argument("--wind-benchmark", default="implementation/phase1/wind_time_history_gate_report.json")
    p.add_argument("--ssi-boundary", default="implementation/phase1/ssi_boundary_gate_report.json")
    p.add_argument("--damper-validation", default="implementation/phase1/damper_validation_gate_report.json")
    p.add_argument("--kds-compliance", default="implementation/phase1/release/kds_compliance/kds_compliance_summary.json")
    p.add_argument("--construction-sequence", default="implementation/phase1/construction_sequence_gate_report.json")
    p.add_argument("--flexible-diaphragm", default="implementation/phase1/flexible_diaphragm_gate_report.json")
    p.add_argument("--repro-version-lock", default="implementation/phase1/reproducibility_version_lock_report.json")
    p.add_argument("--release-registry", default="implementation/phase1/release/release_registry.json")
    p.add_argument("--solver-hip-e2e", default="implementation/phase1/solver_hip_e2e_contract_report.json")
    p.add_argument("--rc-benchmark-lock", default="implementation/phase1/rc_benchmark_lock_report.json")
    p.add_argument("--phasea-contract", default="implementation/phase1/phasea_contract_report.json")
    p.add_argument("--phaseb-track-lf", default="implementation/phase1/track_lf_solver_report.json")
    p.add_argument("--phaseb-moving-load", default="implementation/phase1/moving_load_integrator_report.json")
    p.add_argument("--phaseb-vti", default="implementation/phase1/vti_coupled_solver_report.json")
    p.add_argument("--phaseb-irregularity", default="implementation/phase1/track_irregularity_report.json")
    p.add_argument("--phaseb-summary", default="implementation/phase1/phaseb_track_summary_report.json")
    p.add_argument("--phased-track-dataset", default="implementation/phase1/track_dynamics_dataset_report.json")
    p.add_argument("--phased-tunnel-dataset", default="implementation/phase1/tunnel_dynamics_dataset_report.json")
    p.add_argument("--phased-attention", default="implementation/phase1/moving_load_attention_report.json")
    p.add_argument("--phased-tgnn", default="implementation/phase1/tgnn_multidomain_report.json")
    p.add_argument("--phased-summary", default="implementation/phase1/phased_multidomain_summary_report.json")
    p.add_argument("--phasee-substructuring", default="implementation/phase1/substructuring_interface_report.json")
    p.add_argument("--phasee-attenuation", default="implementation/phase1/vibration_attenuation_report.json")
    p.add_argument("--phasee-compliance", default="implementation/phase1/vibration_compliance_report.json")
    p.add_argument("--phasee-whitebox", default="implementation/phase1/whitebox_validation_report.json")
    p.add_argument("--phasee-summary", default="implementation/phase1/phasee_integrated_summary_report.json")
    p.add_argument("--phasef-l3", default="implementation/phase1/multiscale_l3_streaming_report.json")
    p.add_argument("--phasef-phase-correction", default="implementation/phase1/phase_correction_assimilation_report.json")
    p.add_argument("--phasef-soil-ood", default="implementation/phase1/heterogeneous_soil_ood_report.json")
    p.add_argument("--phasef-summary", default="implementation/phase1/phasef_resilience_summary_report.json")
    p.add_argument("--out", default="implementation/phase1/static_artifact_validation_report.json")
    args = p.parse_args()

    smoke = _load(args.smoke)
    ci = _load(args.ci)
    rca = _load(args.rca)
    priority = _load(args.priority)
    dyn = _load(args.dyn)
    pgat = _load(args.pgat)
    subproj = _load(args.subproj)
    soa = _load(args.soa)
    physics_residual = _load(args.physics_residual)
    meta_learning = _load(args.meta_learning)
    buckling = _load(args.buckling)
    benchmark = _load(args.benchmark)
    branching = _load(args.branching)
    bifurcation = _load(args.bifurcation)
    rust_onnx = _load(args.rust_onnx)
    winning_ticket = _load(args.winning_ticket)
    rust_parity = _load(args.rust_parity)
    lj_mapping = _load(args.lj_mapping)
    dynamic_time_history = _load(args.dynamic_time_history)
    cache_profile = _load(args.cache_profile)
    p0_engine_perf = _load(args.p0_engine_perf)
    p0_core_gap = _load(args.p0_core_gap)
    hip_kernel_smoke = _load(args.hip_kernel_smoke) if Path(args.hip_kernel_smoke).exists() else None
    noise_stress = _load(args.noise_stress)
    scaleout_io = _load(args.scaleout_io)
    nightly_10m_repro = _load(args.nightly_10m_repro)
    ndtha_long_profile = _load(args.ndtha_long_profile) if Path(args.ndtha_long_profile).exists() else None
    phase3_pipeline = _load(args.phase3_pipeline)
    topology_gate = _load(args.topology_gate)
    partitioned_scaleout = _load(args.partitioned_scaleout)
    sync_stress = _load(args.sync_stress)
    noise_convergence = _load(args.noise_convergence)
    commercial_csv_gate = _load(args.commercial_csv_gate)
    midas_mgt_conversion = _load(args.midas_mgt_conversion)
    commercial_readiness = _load(args.commercial_readiness)
    real_source_multi = _load(args.real_source_multi)
    nonlinear_engine = _load(args.nonlinear_engine)
    pushover_stress = _load(args.pushover_stress)
    ndtha_stress = _load(args.ndtha_stress)
    ndtha_residual_gate = _load(args.ndtha_residual_gate)
    pbd_review_package = _load(args.pbd_review_package)
    global_authority_gate = _load(args.global_authority_gate)
    wind_benchmark = _load(args.wind_benchmark)
    ssi_boundary = _load(args.ssi_boundary)
    damper_validation = _load(args.damper_validation)
    kds_compliance = _load(args.kds_compliance)
    construction_sequence = _load(args.construction_sequence)
    flexible_diaphragm = _load(args.flexible_diaphragm)
    repro_version_lock = _load(args.repro_version_lock)
    release_registry = _load(args.release_registry) if Path(args.release_registry).exists() else None
    solver_hip_e2e = _load(args.solver_hip_e2e) if Path(args.solver_hip_e2e).exists() else None
    rc_benchmark_lock = _load(args.rc_benchmark_lock) if Path(args.rc_benchmark_lock).exists() else None
    phasea_contract = _load(args.phasea_contract)
    phaseb_track_lf = _load(args.phaseb_track_lf)
    phaseb_moving_load = _load(args.phaseb_moving_load)
    phaseb_vti = _load(args.phaseb_vti)
    phaseb_irregularity = _load(args.phaseb_irregularity)
    phaseb_summary = _load(args.phaseb_summary)
    phased_track_dataset = _load(args.phased_track_dataset)
    phased_tunnel_dataset = _load(args.phased_tunnel_dataset)
    phased_attention = _load(args.phased_attention)
    phased_tgnn = _load(args.phased_tgnn)
    phased_summary = _load(args.phased_summary)
    phasee_substructuring = _load(args.phasee_substructuring)
    phasee_attenuation = _load(args.phasee_attenuation)
    phasee_compliance = _load(args.phasee_compliance)
    phasee_whitebox = _load(args.phasee_whitebox)
    phasee_summary = _load(args.phasee_summary)
    phasef_l3 = _load(args.phasef_l3)
    phasef_phase_correction = _load(args.phasef_phase_correction)
    phasef_soil_ood = _load(args.phasef_soil_ood)
    phasef_summary = _load(args.phasef_summary)

    errors = {
        "smoke": validate_smoke(smoke),
        "ci": validate_ci(ci),
        "rca": validate_rca(rca),
        "priority": validate_priority(priority),
        "dyn": validate_dyn(dyn),
        "pgat": validate_pgat(pgat),
        "subproj": validate_subproj(subproj),
        "soa": validate_soa(soa),
        "physics_residual": validate_physics_residual(physics_residual),
        "meta_learning": validate_meta_learning(meta_learning),
        "buckling": validate_buckling(buckling),
        "benchmark": validate_benchmark(benchmark),
        "branching": validate_branching(branching),
        "bifurcation": validate_bifurcation(bifurcation),
        "rust_onnx": validate_rust_onnx(rust_onnx),
        "winning_ticket": validate_winning_ticket(winning_ticket),
        "rust_parity": validate_rust_parity(rust_parity),
        "lj_mapping": validate_lj_mapping(lj_mapping),
        "dynamic_time_history": validate_dynamic_time_history(dynamic_time_history),
        "cache_profile": validate_cache_profile(cache_profile),
        "p0_engine_perf": validate_p0_engine_perf(p0_engine_perf),
        "p0_core_gap": validate_p0_core_gap(p0_core_gap),
        "hip_kernel_smoke": validate_hip_kernel_smoke(hip_kernel_smoke) if isinstance(hip_kernel_smoke, dict) else [],
        "noise_stress": validate_noise_stress(noise_stress),
        "scaleout_io": validate_scaleout_io(scaleout_io),
        "nightly_10m_repro": validate_nightly_10m_repro(nightly_10m_repro),
        "ndtha_long_profile": validate_ndtha_long_profile(ndtha_long_profile) if isinstance(ndtha_long_profile, dict) else [],
        "phase3_pipeline": validate_phase3_real_source(phase3_pipeline),
        "topology_gate": validate_topology_gate(topology_gate),
        "partitioned_scaleout": validate_partitioned_scaleout(partitioned_scaleout),
        "sync_stress": validate_sync_stress(sync_stress),
        "noise_convergence": validate_noise_convergence(noise_convergence),
        "commercial_csv_gate": validate_commercial_csv_gate(commercial_csv_gate),
        "midas_mgt_conversion": validate_midas_mgt_conversion(midas_mgt_conversion),
        "commercial_readiness": validate_commercial_readiness(commercial_readiness),
        "real_source_multi": validate_real_source_multi_gate(real_source_multi),
        "nonlinear_engine": validate_nonlinear_engine(nonlinear_engine),
        "pushover_stress": validate_pushover_stress(pushover_stress),
        "ndtha_stress": validate_ndtha_stress(ndtha_stress),
        "ndtha_residual_gate": validate_ndtha_residual_gate(ndtha_residual_gate),
        "pbd_review_package": validate_pbd_review(pbd_review_package),
        "global_authority_gate": validate_global_authority_gate(global_authority_gate),
        "wind_benchmark": validate_wind_benchmark(wind_benchmark),
        "ssi_boundary": validate_ssi_boundary(ssi_boundary),
        "damper_validation": validate_damper_validation(damper_validation),
        "kds_compliance": validate_kds_compliance(kds_compliance),
        "construction_sequence": validate_construction_sequence(construction_sequence),
        "flexible_diaphragm": validate_flexible_diaphragm(flexible_diaphragm),
        "repro_version_lock": validate_repro_version_lock(repro_version_lock),
        "release_registry": validate_release_registry(release_registry) if isinstance(release_registry, dict) else [],
        "solver_hip_e2e": validate_solver_hip_e2e(solver_hip_e2e) if isinstance(solver_hip_e2e, dict) else [],
        "rc_benchmark_lock": validate_rc_benchmark_lock(rc_benchmark_lock) if isinstance(rc_benchmark_lock, dict) else [],
        "phasea_contract": validate_phasea(phasea_contract),
        "phaseb_track_lf": validate_track_lf(phaseb_track_lf),
        "phaseb_moving_load": validate_moving_load(phaseb_moving_load),
        "phaseb_vti": validate_vti(phaseb_vti),
        "phaseb_irregularity": validate_irregularity(phaseb_irregularity),
        "phaseb_summary": validate_phaseb_summary(phaseb_summary),
        "phased_track_dataset": validate_phased_track_dataset(phased_track_dataset),
        "phased_tunnel_dataset": validate_phased_tunnel_dataset(phased_tunnel_dataset),
        "phased_attention": validate_phased_attention(phased_attention),
        "phased_tgnn": validate_phased_tgnn(phased_tgnn),
        "phased_summary": validate_phased_summary(phased_summary),
        "phasee_substructuring": validate_phasee_substructuring(phasee_substructuring),
        "phasee_attenuation": validate_phasee_attenuation(phasee_attenuation),
        "phasee_compliance": validate_phasee_compliance(phasee_compliance),
        "phasee_whitebox": validate_phasee_whitebox(phasee_whitebox),
        "phasee_summary": validate_phasee_summary(phasee_summary),
        "phasef_l3": validate_phasef_l3(phasef_l3),
        "phasef_phase_correction": validate_phasef_phase(phasef_phase_correction),
        "phasef_soil_ood": validate_phasef_soil_ood(phasef_soil_ood),
        "phasef_summary": validate_phasef_summary(phasef_summary),
    }
    all_errors = [e for vs in errors.values() for e in vs]

    report = {
        "schema_version": "1.4",
        "run_id": "phase1-static-artifact-validation",
        "generated_at": "static",
        "pass": len(all_errors) == 0,
        "error_count": len(all_errors),
        "errors": errors,
        "checked_files": {
            "smoke": args.smoke,
            "ci": args.ci,
            "rca": args.rca,
            "priority": args.priority,
            "dyn": args.dyn,
            "pgat": args.pgat,
            "subproj": args.subproj,
            "soa": args.soa,
            "physics_residual": args.physics_residual,
            "meta_learning": args.meta_learning,
            "buckling": args.buckling,
            "benchmark": args.benchmark,
            "branching": args.branching,
            "bifurcation": args.bifurcation,
            "rust_onnx": args.rust_onnx,
            "winning_ticket": args.winning_ticket,
            "rust_parity": args.rust_parity,
            "lj_mapping": args.lj_mapping,
            "dynamic_time_history": args.dynamic_time_history,
            "cache_profile": args.cache_profile,
            "p0_engine_perf": args.p0_engine_perf,
            "p0_core_gap": args.p0_core_gap,
            "hip_kernel_smoke": args.hip_kernel_smoke,
            "noise_stress": args.noise_stress,
            "scaleout_io": args.scaleout_io,
            "nightly_10m_repro": args.nightly_10m_repro,
            "ndtha_long_profile": args.ndtha_long_profile,
            "phase3_pipeline": args.phase3_pipeline,
            "topology_gate": args.topology_gate,
            "partitioned_scaleout": args.partitioned_scaleout,
            "sync_stress": args.sync_stress,
            "noise_convergence": args.noise_convergence,
            "commercial_csv_gate": args.commercial_csv_gate,
            "midas_mgt_conversion": args.midas_mgt_conversion,
            "commercial_readiness": args.commercial_readiness,
            "real_source_multi": args.real_source_multi,
            "nonlinear_engine": args.nonlinear_engine,
            "pushover_stress": args.pushover_stress,
            "ndtha_stress": args.ndtha_stress,
            "ndtha_residual_gate": args.ndtha_residual_gate,
            "pbd_review_package": args.pbd_review_package,
            "global_authority_gate": args.global_authority_gate,
            "wind_benchmark": args.wind_benchmark,
            "ssi_boundary": args.ssi_boundary,
            "damper_validation": args.damper_validation,
            "kds_compliance": args.kds_compliance,
            "construction_sequence": args.construction_sequence,
            "flexible_diaphragm": args.flexible_diaphragm,
            "repro_version_lock": args.repro_version_lock,
            "release_registry": args.release_registry,
            "solver_hip_e2e": args.solver_hip_e2e,
            "rc_benchmark_lock": args.rc_benchmark_lock,
            "phasea_contract": args.phasea_contract,
            "phaseb_track_lf": args.phaseb_track_lf,
            "phaseb_moving_load": args.phaseb_moving_load,
            "phaseb_vti": args.phaseb_vti,
            "phaseb_irregularity": args.phaseb_irregularity,
            "phaseb_summary": args.phaseb_summary,
            "phased_track_dataset": args.phased_track_dataset,
            "phased_tunnel_dataset": args.phased_tunnel_dataset,
            "phased_attention": args.phased_attention,
            "phased_tgnn": args.phased_tgnn,
            "phased_summary": args.phased_summary,
            "phasee_substructuring": args.phasee_substructuring,
            "phasee_attenuation": args.phasee_attenuation,
            "phasee_compliance": args.phasee_compliance,
            "phasee_whitebox": args.phasee_whitebox,
            "phasee_summary": args.phasee_summary,
            "phasef_l3": args.phasef_l3,
            "phasef_phase_correction": args.phasef_phase_correction,
            "phasef_soil_ood": args.phasef_soil_ood,
            "phasef_summary": args.phasef_summary,
        },
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote static artifact validation report: {args.out}")
    if all_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
