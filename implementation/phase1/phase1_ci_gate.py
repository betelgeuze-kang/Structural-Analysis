#!/usr/bin/env python3
"""CI gate checker: validates strict probe + RCA + static contract artifacts.

Mobile-web friendly behavior:
- strict JSON shape/range checks (no runtime engine calls)
- deterministic reason_code output for CI debugging
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import math
from pathlib import Path


REASON_CODES = {
    "PASS": "all gates satisfied",
    "ERR_MISSING_STRICT_KEY": "strict report missing required key",
    "ERR_MISSING_RCA_KEY": "rca report missing required key",
    "ERR_INVALID_RCA_VALUE": "rca value is non-numeric or out-of-range",
    "ERR_STRICT_FAIL": "strict rust/hip pass flag is false",
    "ERR_HOST_COPY_SHARE": "host copy share exceeds configured threshold",
    "ERR_MISSING_CONTRACT_ARTIFACT": "one or more required static contract artifacts are missing or invalid",
    "ERR_PRIORITY3_FAIL": "priority3 summary indicates failure or invalid reason code",
    "ERR_BUCKLING_EIGEN_INVALID": "buckling eigen contract report failed validation",
    "ERR_ENERGY_MONOTONICITY": "physics residual energy monotonicity check failed",
    "ERR_META_OOD_FAIL": "meta-learning report does not satisfy OOD generalization minimum",
    "ERR_BENCHMARK_KPI_FAIL": "high-fidelity benchmark KPI contract failed",
    "ERR_BRANCHING_CONTRACT_FAIL": "derivative-free physical branching contract failed",
    "ERR_BIFURCATION_CONTRACT_FAIL": "bifurcation detector contract missing trigger readiness",
    "ERR_RUST_ONNX_CONTRACT_FAIL": "rust/hip/onnx native contract failed",
    "ERR_WINNING_TICKET_FAIL": "winning-ticket backprop contract failed",
}


def _is_finite_non_negative(x: object) -> bool:
    try:
        v = float(x)
    except Exception:
        return False
    return math.isfinite(v) and v >= 0.0


def _validate_inputs(strict: dict, rca: dict) -> tuple[bool, str]:
    if "strict_rust_hip_pass" not in strict:
        return False, "ERR_MISSING_STRICT_KEY"

    if "timing_breakdown_seconds" not in rca:
        return False, "ERR_MISSING_RCA_KEY"

    timing = rca.get("timing_breakdown_seconds")
    if not isinstance(timing, dict):
        return False, "ERR_MISSING_RCA_KEY"

    for key in ("compute", "host_copy", "serialization"):
        if key not in timing:
            return False, "ERR_MISSING_RCA_KEY"
        if not _is_finite_non_negative(timing[key]):
            return False, "ERR_INVALID_RCA_VALUE"

    return True, "PASS"


def _validate_contract_artifacts(paths: list[str]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for p in paths:
        fp = Path(p)
        if not fp.exists():
            missing.append(p)
            continue
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            missing.append(p)
            continue
        # contract report must explicitly contain pass boolean
        if not bool(payload.get("contract_pass", payload.get("layout_pass", False))):
            missing.append(p)
    return len(missing) == 0, missing




def _validate_priority3(path: str | None) -> tuple[bool, str | None, dict | None]:
    if not path:
        return True, None, None
    p = Path(path)
    if not p.exists():
        return False, "ERR_PRIORITY3_FAIL", None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False, "ERR_PRIORITY3_FAIL", None
    allowed = {"PASS", "ERR_MODULE_FAIL", "ERR_METADATA_VERSION_MISMATCH"}
    if data.get("reason_code") not in allowed:
        return False, "ERR_PRIORITY3_FAIL", data
    if not bool(data.get("all_pass", False)):
        return False, "ERR_PRIORITY3_FAIL", data
    return True, None, data



def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _validate_extended_contracts(
    physics_path: str,
    meta_path: str,
    buckling_path: str,
    benchmark_path: str,
    branching_path: str,
    bifurcation_path: str,
    rust_onnx_path: str,
    winning_ticket_path: str,
) -> tuple[bool, bool, bool, bool, bool, bool, bool, bool]:
    physics = _load_json(physics_path)
    meta = _load_json(meta_path)
    buckling = _load_json(buckling_path)
    benchmark = _load_json(benchmark_path)
    branching = _load_json(branching_path)
    bifurcation = _load_json(bifurcation_path)
    rust_onnx = _load_json(rust_onnx_path)
    winning_ticket = _load_json(winning_ticket_path)

    energy_ok = bool(physics.get("checks", {}).get("energy_monotonicity_pass", False))
    meta_ood_ok = bool(meta.get("meta_ood_generalization_pass", False))
    buckling_ok = bool(buckling.get("contract_pass", False)) and float(buckling.get("critical_load_factor", 0.0)) > 0.0
    benchmark_ok = bool(benchmark.get("contract_pass", False)) and bool(benchmark.get("kpi_pass", False))
    branching_ok = bool(branching.get("contract_pass", False)) and not bool(branching.get("uses_backprop", True))
    bifurcation_ok = bool(bifurcation.get("contract_pass", False)) and isinstance(bifurcation.get("trigger", {}).get("triggered"), bool)
    rust_onnx_ok = bool(rust_onnx.get("contract_pass", False))
    winning_ticket_ok = bool(winning_ticket.get("contract_pass", False)) and bool(winning_ticket.get("uses_backprop", False)) and int(winning_ticket.get("targeted_backprop", {}).get("graph_count", 0)) == 1
    return energy_ok, meta_ood_ok, buckling_ok, benchmark_ok, branching_ok, bifurcation_ok, rust_onnx_ok, winning_ticket_ok


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--strict-probe", default="implementation/phase1/zero_copy_real_probe_report_strict.json")
    p.add_argument("--rca", default="implementation/phase1/step_outputs/step5_rca_summary.json")
    p.add_argument("--max-host-copy-share", type=float, default=0.2)
    p.add_argument("--out", default="implementation/phase1/ci_gate_report.json")
    p.add_argument("--manifest", default="implementation/phase1/ci_artifact_manifest.json")
    p.add_argument("--priority3", default=None, help="optional priority3 summary path")
    p.add_argument("--physics-residual", default="implementation/phase1/physics_residual_contract_report.json")
    p.add_argument("--meta-learning", default="implementation/phase1/meta_learning_task_report.json")
    p.add_argument("--buckling", default="implementation/phase1/buckling_contract_report.json")
    p.add_argument("--benchmark", default="implementation/phase1/hf_benchmark_report.json")
    p.add_argument("--branching", default="implementation/phase1/physics_branching_report.json")
    p.add_argument("--bifurcation", default="implementation/phase1/bifurcation_detector_report.json")
    p.add_argument("--rust-onnx", default="implementation/phase1/rust_onnx_native_contract_report.json")
    p.add_argument("--winning-ticket", default="implementation/phase1/winning_ticket_backprop_report.json")
    p.add_argument(
        "--required-contracts",
        nargs="*",
        default=[
            "implementation/phase1/dynamics_boundary_report.json",
            "implementation/phase1/pg_gat_contract_report.json",
            "implementation/phase1/subgraph_projection_report.json",
            "implementation/phase1/soa_dlpack_contract_report.json",
            "implementation/phase1/physics_residual_contract_report.json",
            "implementation/phase1/meta_learning_task_report.json",
            "implementation/phase1/buckling_contract_report.json",
            "implementation/phase1/hf_benchmark_report.json",
            "implementation/phase1/physics_branching_report.json",
            "implementation/phase1/bifurcation_detector_report.json",
            "implementation/phase1/rust_onnx_native_contract_report.json",
            "implementation/phase1/winning_ticket_backprop_report.json",
        ],
        help="additional static contract artifacts required by gate",
    )
    args = p.parse_args()

    strict = json.loads(Path(args.strict_probe).read_text(encoding="utf-8"))
    rca = json.loads(Path(args.rca).read_text(encoding="utf-8"))

    inputs_ok, input_reason = _validate_inputs(strict, rca)
    contracts_ok, missing_contracts = _validate_contract_artifacts(args.required_contracts)
    priority_ok, priority_reason, priority_data = _validate_priority3(args.priority3)
    energy_ok, meta_ood_ok, buckling_ok, benchmark_ok, branching_ok, bifurcation_ok, rust_onnx_ok, winning_ticket_ok = _validate_extended_contracts(
        args.physics_residual, args.meta_learning, args.buckling, args.benchmark,
        args.branching, args.bifurcation, args.rust_onnx, args.winning_ticket
    )

    if not inputs_ok:
        report = {
            "strict_rust_hip_pass": bool(strict.get("strict_rust_hip_pass", False)),
            "host_copy_share": None,
            "host_copy_share_limit": args.max_host_copy_share,
            "host_copy_share_pass": False,
            "contract_artifacts_pass": contracts_ok,
            "missing_contract_artifacts": missing_contracts,
            "priority3_checked": bool(args.priority3),
            "priority3_pass": priority_ok,
            "all_pass": False,
            "reason_code": input_reason,
            "reason": REASON_CODES[input_reason],
        }
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        raise SystemExit(1)

    strict_ok = bool(strict["strict_rust_hip_pass"])
    timing = rca["timing_breakdown_seconds"]
    total = float(timing["compute"]) + float(timing["host_copy"]) + float(timing["serialization"])
    host_share = 0.0 if total <= 1e-12 else float(timing.get("host_copy", 0.0)) / total
    host_copy_ok = host_share <= args.max_host_copy_share

    if not contracts_ok:
        reason_code = "ERR_MISSING_CONTRACT_ARTIFACT"
    elif not buckling_ok:
        reason_code = "ERR_BUCKLING_EIGEN_INVALID"
    elif not energy_ok:
        reason_code = "ERR_ENERGY_MONOTONICITY"
    elif not meta_ood_ok:
        reason_code = "ERR_META_OOD_FAIL"
    elif not benchmark_ok:
        reason_code = "ERR_BENCHMARK_KPI_FAIL"
    elif not branching_ok:
        reason_code = "ERR_BRANCHING_CONTRACT_FAIL"
    elif not bifurcation_ok:
        reason_code = "ERR_BIFURCATION_CONTRACT_FAIL"
    elif not rust_onnx_ok:
        reason_code = "ERR_RUST_ONNX_CONTRACT_FAIL"
    elif not winning_ticket_ok:
        reason_code = "ERR_WINNING_TICKET_FAIL"
    elif not priority_ok:
        reason_code = "ERR_PRIORITY3_FAIL"
    elif not strict_ok:
        reason_code = "ERR_STRICT_FAIL"
    elif not host_copy_ok:
        reason_code = "ERR_HOST_COPY_SHARE"
    else:
        reason_code = "PASS"

    report = {
        "schema_version": "1.5",
        "run_id": "phase1-ci-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strict_rust_hip_pass": strict_ok,
        "host_copy_share": host_share,
        "host_copy_share_limit": args.max_host_copy_share,
        "host_copy_share_pass": host_copy_ok,
        "contract_artifacts_pass": contracts_ok,
        "missing_contract_artifacts": missing_contracts,
        "priority3_checked": bool(args.priority3),
        "priority3_pass": priority_ok,
        "priority3_reason_code": None if priority_ok else priority_reason,
        "physics_energy_monotonic_pass": energy_ok,
        "meta_ood_generalization_pass": meta_ood_ok,
        "buckling_contract_pass": buckling_ok,
        "benchmark_kpi_pass": benchmark_ok,
        "branching_contract_pass": branching_ok,
        "bifurcation_contract_pass": bifurcation_ok,
        "rust_onnx_contract_pass": rust_onnx_ok,
        "winning_ticket_contract_pass": winning_ticket_ok,
        "all_pass": strict_ok and host_copy_ok and contracts_ok and energy_ok and meta_ood_ok and buckling_ok and benchmark_ok and branching_ok and bifurcation_ok and rust_onnx_ok and winning_ticket_ok and priority_ok,
        "reason_code": reason_code,
        "reason": REASON_CODES[reason_code],
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "1.5",
        "run_id": "phase1-ci-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": [
            args.strict_probe,
            args.rca,
            args.out,
            *args.required_contracts,
            *( [args.priority3] if args.priority3 else [] ),
        ],
    }
    Path(args.manifest).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote CI gate report: {args.out}")
    print(f"Wrote artifact manifest: {args.manifest}")
    if not report["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
