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
    for key in ("strict_rust_hip_pass", "host_copy_share_pass", "all_pass", "contract_artifacts_pass", "branching_contract_pass", "bifurcation_contract_pass", "rust_onnx_contract_pass", "winning_ticket_contract_pass"):
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
        if not isinstance(sel.get("winner_branch_id"), int):
            errs.append("winning_ticket.selection.winner_branch_id invalid")

    tb = report.get("targeted_backprop")
    if not isinstance(tb, dict):
        errs.append("winning_ticket.targeted_backprop missing")
    else:
        if int(tb.get("graph_count", 0)) != 1:
            errs.append("winning_ticket.targeted_backprop.graph_count must be 1")
        if not isinstance(tb.get("success"), bool):
            errs.append("winning_ticket.targeted_backprop.success invalid")
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
    }
    all_errors = [e for vs in errors.values() for e in vs]

    report = {
        "schema_version": "1.1",
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
        },
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote static artifact validation report: {args.out}")
    if all_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
