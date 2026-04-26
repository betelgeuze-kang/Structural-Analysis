#!/usr/bin/env python3
"""Run virtual sync stress gate over partitioned scaleout levels."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "sync stress gate passed",
    "ERR_INVALID_INPUT": "invalid sync stress gate input",
    "ERR_TOPOLOGY_GATE": "topology gate failed",
    "ERR_BACKEND_POLICY": "sync backend policy failed",
    "ERR_LEVEL_RUN": "sync backend run failed on one or more levels",
    "ERR_SYNC_BUDGET": "sync budget failed on required levels",
    "ERR_INLINE_NATIVE_SMOKE": "inline-native sync smoke gate failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["partitioned_scaleout", "out"],
    "properties": {
        "partitioned_scaleout": {"type": "string", "minLength": 1},
        "topology_report": {"type": "string", "minLength": 1},
        "require_topology_gate": {"type": "boolean"},
        "sync_backend": {"type": "string", "enum": ["feti_lite", "virtual"]},
        "feti_execution_mode": {"type": "string", "enum": ["emulation", "boundary_sync"]},
        "require_feti_backend": {"type": "boolean"},
        "allow_virtual_sync": {"type": "boolean"},
        "ci_mode": {"type": "string", "enum": ["pr", "nightly"]},
        "steps": {"type": "integer", "minimum": 10},
        "bandwidth_gbps": {"type": "number", "exclusiveMinimum": 0.0},
        "latency_us": {"type": "number", "minimum": 0.0},
        "compute_us_per_node": {"type": "number", "exclusiveMinimum": 0.0},
        "overlap_cap": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "jitter_pct": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_sync_stall_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_p99_step_ms": {"type": "number", "exclusiveMinimum": 0.0},
        "max_straggler_ratio": {"type": "number", "exclusiveMinimum": 1.0},
        "min_overlap_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "max_feti_iters": {"type": "integer", "minimum": 1},
        "feti_gap_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_force_tol": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_rho": {"type": "number", "exclusiveMinimum": 0.0},
        "feti_relax": {"type": "number", "exclusiveMinimum": 0.0, "maximum": 1.0},
        "feti_min_converged_step_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "strict_feti_profile": {"type": "boolean"},
        "min_bandwidth_gbps": {"type": "number", "exclusiveMinimum": 0.0},
        "max_latency_us": {"type": "number", "minimum": 0.0},
        "work_dir": {"type": "string", "minLength": 1},
        "require_inline_native_smoke": {"type": "boolean"},
        "inline_native_ground_motion_csv": {"type": "string", "minLength": 1},
        "inline_native_target_dof": {"type": "integer", "minimum": 0},
        "inline_native_max_steps": {"type": "integer", "minimum": 10},
        "inline_native_min_load_reversals": {"type": "integer", "minimum": 1},
        "inline_native_report": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run(step: str, cmd: list[str], logs: list[dict]) -> bool:
    t0 = time.time()
    proc = subprocess.run(cmd, text=True, capture_output=True)
    logs.append(
        {
            "step": step,
            "seconds": float(time.time() - t0),
            "return_code": int(proc.returncode),
            "command": shlex.join(cmd),
            "stdout_tail": (proc.stdout or "")[-1600:],
            "stderr_tail": (proc.stderr or "")[-1600:],
        }
    )
    return proc.returncode == 0


def main() -> None:
    logger = get_logger("phase3.run_sync_stress_gate")
    p = argparse.ArgumentParser()
    p.add_argument("--partitioned-scaleout", default="implementation/phase1/partitioned_scaleout_report.json")
    p.add_argument("--topology-report", default="implementation/phase1/opensees_topology_report.json")
    p.add_argument("--require-topology-gate", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--sync-backend", choices=["feti_lite", "virtual"], default="feti_lite")
    p.add_argument("--feti-execution-mode", choices=["emulation", "boundary_sync"], default="boundary_sync")
    p.add_argument("--require-feti-backend", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--allow-virtual-sync", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--strict-feti-profile", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--ci-mode", choices=["pr", "nightly"], default="pr")
    p.add_argument("--steps", type=int, default=300)
    p.add_argument("--bandwidth-gbps", type=float, default=768.0)
    p.add_argument("--latency-us", type=float, default=0.5)
    p.add_argument("--min-bandwidth-gbps", type=float, default=256.0)
    p.add_argument("--max-latency-us", type=float, default=1.5)
    p.add_argument("--compute-us-per-node", type=float, default=0.20)
    p.add_argument("--overlap-cap", type=float, default=0.70)
    p.add_argument("--jitter-pct", type=float, default=0.12)
    p.add_argument("--max-sync-stall-ratio", type=float, default=0.36)
    p.add_argument("--max-p99-step-ms", type=float, default=550.0)
    p.add_argument("--max-straggler-ratio", type=float, default=2.4)
    p.add_argument("--min-overlap-ratio", type=float, default=0.35)
    p.add_argument("--max-feti-iters", type=int, default=12)
    p.add_argument("--feti-gap-tol", type=float, default=8e-4)
    p.add_argument("--feti-force-tol", type=float, default=1e-3)
    p.add_argument("--feti-rho", type=float, default=0.6)
    p.add_argument("--feti-relax", type=float, default=0.45)
    p.add_argument("--feti-min-converged-step-ratio", type=float, default=1.0)
    p.add_argument("--require-inline-native-smoke", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--inline-native-ground-motion-csv", default="implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv")
    p.add_argument("--inline-native-target-dof", type=int, default=0)
    p.add_argument("--inline-native-max-steps", type=int, default=800)
    p.add_argument("--inline-native-min-load-reversals", type=int, default=10)
    p.add_argument("--inline-native-report", default="implementation/phase1/stress/sync/sync_inline_native_smoke.json")
    p.add_argument("--work-dir", default="implementation/phase1/stress/sync")
    p.add_argument("--out", default="implementation/phase1/sync_stress_gate_report.json")
    args = p.parse_args()

    input_payload = {
        "partitioned_scaleout": str(args.partitioned_scaleout),
        "topology_report": str(args.topology_report),
        "require_topology_gate": bool(args.require_topology_gate),
        "sync_backend": str(args.sync_backend),
        "feti_execution_mode": str(args.feti_execution_mode),
        "require_feti_backend": bool(args.require_feti_backend),
        "allow_virtual_sync": bool(args.allow_virtual_sync),
        "ci_mode": str(args.ci_mode),
        "steps": int(args.steps),
        "bandwidth_gbps": float(args.bandwidth_gbps),
        "latency_us": float(args.latency_us),
        "strict_feti_profile": bool(args.strict_feti_profile),
        "min_bandwidth_gbps": float(args.min_bandwidth_gbps),
        "max_latency_us": float(args.max_latency_us),
        "compute_us_per_node": float(args.compute_us_per_node),
        "overlap_cap": float(args.overlap_cap),
        "jitter_pct": float(args.jitter_pct),
        "max_sync_stall_ratio": float(args.max_sync_stall_ratio),
        "max_p99_step_ms": float(args.max_p99_step_ms),
        "max_straggler_ratio": float(args.max_straggler_ratio),
        "min_overlap_ratio": float(args.min_overlap_ratio),
        "max_feti_iters": int(args.max_feti_iters),
        "feti_gap_tol": float(args.feti_gap_tol),
        "feti_force_tol": float(args.feti_force_tol),
        "feti_rho": float(args.feti_rho),
        "feti_relax": float(args.feti_relax),
        "feti_min_converged_step_ratio": float(args.feti_min_converged_step_ratio),
        "require_inline_native_smoke": bool(args.require_inline_native_smoke),
        "inline_native_ground_motion_csv": str(args.inline_native_ground_motion_csv),
        "inline_native_target_dof": int(args.inline_native_target_dof),
        "inline_native_max_steps": int(args.inline_native_max_steps),
        "inline_native_min_load_reversals": int(args.inline_native_min_load_reversals),
        "inline_native_report": str(args.inline_native_report),
        "work_dir": str(args.work_dir),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_sync_stress_gate")

        pscale = _load(str(args.partitioned_scaleout))
        topo = _load(str(args.topology_report)) if Path(args.topology_report).exists() else {}

        topology_ok = bool(topo.get("contract_pass", False)) and bool((topo.get("checks") or {}).get("real_topology_pass", False))
        if bool(args.require_topology_gate) and not topology_ok:
            reason_code = "ERR_TOPOLOGY_GATE"
            level_rows = []
            steps = []
        else:
            reason_code = "PASS"
            if str(args.sync_backend) == "virtual" and not bool(args.allow_virtual_sync):
                reason_code = "ERR_BACKEND_POLICY"
                level_rows = []
                steps = []
            elif bool(args.strict_feti_profile) and (
                float(args.bandwidth_gbps) < float(args.min_bandwidth_gbps)
                or float(args.latency_us) > float(args.max_latency_us)
            ):
                reason_code = "ERR_BACKEND_POLICY"
                level_rows = []
                steps = []
            else:
                work_dir = Path(args.work_dir)
                work_dir.mkdir(parents=True, exist_ok=True)
                steps: list[dict] = []
                level_rows: list[dict] = []

                for row in (pscale.get("level_rows") or []):
                    n = int(row.get("node_count", 0))
                    partition_report = str(row.get("partition_report", ""))
                    if not partition_report:
                        level_rows.append({"node_count": n, "contract_pass": False, "reason_code": "ERR_LEVEL_RUN"})
                        continue
                    out_level = work_dir / f"sync_virtual_n{n}.json"
                    if str(args.sync_backend) == "feti_lite":
                        cmd = [
                            sys.executable,
                            "implementation/phase1/feti_lite_single_gpu.py",
                            "--partition-report",
                            partition_report,
                            "--execution-mode",
                            str(args.feti_execution_mode),
                            "--steps",
                            str(int(args.steps)),
                            "--bandwidth-gbps",
                            str(float(args.bandwidth_gbps)),
                            "--latency-us",
                            str(float(args.latency_us)),
                            "--compute-us-per-node",
                            str(float(args.compute_us_per_node)),
                            "--overlap-cap",
                            str(float(args.overlap_cap)),
                            "--jitter-pct",
                            str(float(args.jitter_pct)),
                            "--max-feti-iters",
                            str(int(args.max_feti_iters)),
                            "--gap-tol",
                            str(float(args.feti_gap_tol)),
                            "--force-tol",
                            str(float(args.feti_force_tol)),
                            "--rho",
                            str(float(args.feti_rho)),
                            "--relax",
                            str(float(args.feti_relax)),
                            "--min-converged-step-ratio",
                            str(float(args.feti_min_converged_step_ratio)),
                            "--max-sync-stall-ratio",
                            str(float(args.max_sync_stall_ratio)),
                            "--max-p99-step-ms",
                            str(float(args.max_p99_step_ms)),
                            "--max-straggler-ratio",
                            str(float(args.max_straggler_ratio)),
                            "--min-overlap-ratio",
                            str(float(args.min_overlap_ratio)),
                            "--out",
                            str(out_level),
                        ]
                    else:
                        cmd = [
                            sys.executable,
                            "implementation/phase1/virtual_partition_sync_emulator.py",
                            "--partition-report",
                            partition_report,
                            "--steps",
                            str(int(args.steps)),
                            "--bandwidth-gbps",
                            str(float(args.bandwidth_gbps)),
                            "--latency-us",
                            str(float(args.latency_us)),
                            "--compute-us-per-node",
                            str(float(args.compute_us_per_node)),
                            "--overlap-cap",
                            str(float(args.overlap_cap)),
                            "--jitter-pct",
                            str(float(args.jitter_pct)),
                            "--max-sync-stall-ratio",
                            str(float(args.max_sync_stall_ratio)),
                            "--max-p99-step-ms",
                            str(float(args.max_p99_step_ms)),
                            "--max-straggler-ratio",
                            str(float(args.max_straggler_ratio)),
                            "--min-overlap-ratio",
                            str(float(args.min_overlap_ratio)),
                            "--out",
                            str(out_level),
                        ]
                    ok = _run(f"sync_emulate_n{n}", cmd, steps)
                    rep = _load(str(out_level)) if out_level.exists() else {}
                    rep_result = rep.get("result") if isinstance(rep.get("result"), dict) else {}
                    backend = str(
                        rep_result.get("backend", "virtual_sync_emulator" if str(args.sync_backend) == "virtual" else "")
                    )
                    feti_iter_p95 = float(rep_result.get("p95_feti_iterations", 0.0))
                    conv_ratio = float(rep_result.get("converged_step_ratio", 0.0))
                    level_rows.append(
                        {
                            "node_count": int(n),
                            "report": str(out_level),
                            "contract_pass": bool(ok and rep.get("contract_pass", False)),
                            "reason_code": str(rep.get("reason_code", "ERR_LEVEL_RUN")),
                            "backend": backend,
                            "converged_step_ratio": conv_ratio,
                            "p95_feti_iterations": feti_iter_p95,
                            "sync_stall_ratio": float((rep.get("result") or {}).get("sync_stall_ratio", 1.0)),
                            "p99_step_ms": float((rep.get("result") or {}).get("p99_step_ms", 1e9)),
                            "straggler_ratio": float((rep.get("result") or {}).get("straggler_ratio", 1e9)),
                            "comm_overlap_ratio": float((rep.get("result") or {}).get("comm_overlap_ratio", 0.0)),
                        }
                    )

            by_n = {int(r.get("node_count", 0)): r for r in level_rows}
            required = (1_000_000, 3_000_000) if str(args.ci_mode) != "nightly" else (1_000_000, 3_000_000, 10_000_000)
            required_present = bool(all(r in by_n for r in required))

            if reason_code == "PASS":
                required_sync_pass = bool(required_present and all(bool(by_n[n].get("contract_pass", False)) for n in required))
                sync_stall_budget_pass = bool(
                    required_present
                    and all(float(by_n[n].get("sync_stall_ratio", 1.0)) <= float(args.max_sync_stall_ratio) for n in required)
                )
                backend_policy_pass = bool(
                    (not bool(args.require_feti_backend))
                    or all(str(by_n[n].get("backend", "")).startswith("feti_lite") for n in required)
                )

                if not required_present:
                    reason_code = "ERR_SYNC_BUDGET"
                elif any(not bool(r.get("contract_pass", False)) for r in level_rows):
                    reason_code = "ERR_LEVEL_RUN"
                elif not backend_policy_pass:
                    reason_code = "ERR_BACKEND_POLICY"
                elif not required_sync_pass or not sync_stall_budget_pass:
                    reason_code = "ERR_SYNC_BUDGET"
            else:
                required_sync_pass = False
                sync_stall_budget_pass = False
                backend_policy_pass = False

        inline_native_smoke_report = str(args.inline_native_report)
        inline_native_smoke_pass = not bool(args.require_inline_native_smoke)
        inline_native_result: dict = {}
        if reason_code == "PASS" and bool(args.require_inline_native_smoke):
            target_dof = int(args.inline_native_target_dof)
            if target_dof <= 0:
                target_dof = min(max(required), 3_000_000)
            cmd_inline = [
                sys.executable,
                "implementation/phase1/run_mega_ndtha_partitioned_stress.py",
                "--partitioned-scaleout",
                str(args.partitioned_scaleout),
                "--topology-report",
                str(args.topology_report),
                "--ground-motion-csv",
                str(args.inline_native_ground_motion_csv),
                "--target-dof",
                str(int(target_dof)),
                "--sync-backend",
                "inline_native",
                "--no-allow-feti-sync",
                "--no-allow-virtual-sync",
                "--require-shell-beam-mix",
                "--require-real-topology",
                "--no-require-full-duration",
                "--max-steps",
                str(int(args.inline_native_max_steps)),
                "--min-load-reversals",
                str(int(args.inline_native_min_load_reversals)),
                "--out",
                str(args.inline_native_report),
            ]
            ok_inline = _run("inline_native_sync_smoke", cmd_inline, steps)
            rep_inline = _load(str(args.inline_native_report)) if Path(args.inline_native_report).exists() else {}
            inline_native_result = rep_inline
            rep_checks = rep_inline.get("checks") if isinstance(rep_inline.get("checks"), dict) else {}
            rep_sync = rep_inline.get("sync_result") if isinstance(rep_inline.get("sync_result"), dict) else {}
            rep_summary = rep_inline.get("summary") if isinstance(rep_inline.get("summary"), dict) else {}
            rep_backend = str(rep_sync.get("backend", "")).strip().lower()
            summary_backend = str(rep_summary.get("sync_backend", "")).strip().lower()
            inline_native_smoke_pass = bool(
                (
                    ok_inline
                    or bool(rep_inline)
                )
                and bool(rep_checks.get("rust_backend_used_pass", False))
                and bool(rep_checks.get("sync_backend_policy_pass", False))
                and int(rep_summary.get("ground_motion_step_count_used", 0)) > 0
                and ("inline_native" in rep_backend or "inline_native" in summary_backend)
            )
            if reason_code == "PASS" and not inline_native_smoke_pass:
                reason_code = "ERR_INLINE_NATIVE_SMOKE"

        checks = {
            "topology_gate_pass": bool(topology_ok),
            "virtual_sync_blocked_pass": bool(
                str(args.sync_backend) != "virtual" or bool(args.allow_virtual_sync)
            ),
            "feti_profile_pass": bool(
                str(args.sync_backend) != "feti_lite"
                or not bool(args.strict_feti_profile)
                or (
                    float(args.bandwidth_gbps) >= float(args.min_bandwidth_gbps)
                    and float(args.latency_us) <= float(args.max_latency_us)
                )
            ),
            "required_levels_present": bool(required_present),
            "required_levels_sync_pass": bool(
                reason_code == "PASS" or reason_code == "ERR_SYNC_BUDGET"
            ) and bool(all(bool(r.get("contract_pass", False)) for r in level_rows if int(r.get("node_count", 0)) in required)),
            "sync_stall_budget_pass": bool(all(float(r.get("sync_stall_ratio", 1.0)) <= float(args.max_sync_stall_ratio) for r in level_rows if int(r.get("node_count", 0)) in required)),
            "backend_policy_pass": bool(
                (not bool(args.require_feti_backend))
                or all(
                    str(r.get("backend", "")).startswith("feti_lite")
                    for r in level_rows
                    if int(r.get("node_count", 0)) in required
                )
            ),
            "inline_native_smoke_required": bool(args.require_inline_native_smoke),
            "inline_native_smoke_pass": bool(inline_native_smoke_pass),
        }
        contract_pass = bool(reason_code == "PASS")

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-sync-stress-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "reports": {
                "partitioned_scaleout": str(args.partitioned_scaleout),
                "topology_report": str(args.topology_report),
                "inline_native_smoke_report": inline_native_smoke_report,
            },
            "checks": checks,
            "level_rows": level_rows,
            "inline_native_smoke_result": inline_native_result,
            "steps": steps,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, 20, "sync_stress_gate.completed", contract_pass=contract_pass, reason_code=reason_code)
        print(f"Wrote sync stress gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-sync-stress-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote sync stress gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
