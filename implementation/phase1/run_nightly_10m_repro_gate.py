#!/usr/bin/env python3
"""Nightly 10M reproducibility gate via repeated partitioned scale-out runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shlex
import statistics
import subprocess
import sys
import time

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "nightly 10m reproducibility gate passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_RUN_FAIL": "one or more nightly runs failed",
    "ERR_MISSING_10M_ROW": "10m level row missing from one or more runs",
    "ERR_VARIANCE_TOO_HIGH": "cross-run variance exceeds reproducibility threshold",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "runs",
        "dof_levels",
        "edge_list_json",
        "gpu_strict",
        "max_cov_latency_10m",
        "max_cov_working_set_10m",
        "out",
    ],
    "properties": {
        "runs": {"type": "integer", "minimum": 2},
        "dof_levels": {"type": "string", "minLength": 1},
        "edge_list_json": {"type": "string", "minLength": 1},
        "gpu_strict": {"type": "boolean"},
        "allow_cpu_required": {"type": "boolean"},
        "partition_max_projection_ratio": {"type": "number", "minimum": 0.0},
        "max_cov_latency_10m": {"type": "number", "minimum": 0.0},
        "max_cov_working_set_10m": {"type": "number", "minimum": 0.0},
        "work_dir": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _run(cmd: list[str]) -> tuple[bool, float, int, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    return (
        proc.returncode == 0,
        dt,
        int(proc.returncode),
        (proc.stdout or "")[-1600:],
        (proc.stderr or "")[-1600:],
    )


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cov(xs: list[float]) -> float:
    if len(xs) < 2:
        return math.inf
    mu = statistics.fmean(xs)
    if abs(mu) <= 1e-12:
        return math.inf
    return float(statistics.pstdev(xs) / abs(mu))


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="nightly_10m_repro_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--dof-levels", default="1000000,3000000,10000000")
    p.add_argument("--edge-list-json", default="implementation/phase1/open_data/megastructure/opensees_edges.json")
    p.add_argument("--gpu-strict", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--allow-cpu-required", action="store_true")
    p.add_argument("--partition-max-projection-ratio", type=float, default=2000.0)
    p.add_argument("--max-cov-latency-10m", type=float, default=0.15)
    p.add_argument("--max-cov-working-set-10m", type=float, default=0.15)
    p.add_argument("--work-dir", default="implementation/phase1/stress/nightly_10m_repro")
    p.add_argument("--out", default="implementation/phase1/nightly_10m_repro_report.json")
    args = p.parse_args()

    input_payload = {
        "runs": int(args.runs),
        "dof_levels": str(args.dof_levels),
        "edge_list_json": str(args.edge_list_json),
        "gpu_strict": bool(args.gpu_strict),
        "allow_cpu_required": bool(args.allow_cpu_required),
        "partition_max_projection_ratio": float(args.partition_max_projection_ratio),
        "max_cov_latency_10m": float(args.max_cov_latency_10m),
        "max_cov_working_set_10m": float(args.max_cov_working_set_10m),
        "work_dir": str(args.work_dir),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_nightly_10m_repro_gate")
        run_rows: list[dict] = []
        report_paths: list[str] = []
        lat_10m: list[float] = []
        ws_10m: list[float] = []
        all_runs_ok = True
        has_10m_rows = True

        for i in range(int(args.runs)):
            run_out = work_dir / f"partitioned_scaleout_run{i+1}.json"
            cmd = [
                sys.executable,
                "implementation/phase1/run_partitioned_scaleout.py",
                "--dof-levels",
                str(args.dof_levels),
                "--branches",
                "64",
                "--chunk-candidates",
                "64,32,16,8,4,2,1",
                "--ci-mode",
                "nightly",
                "--edge-list-json",
                str(args.edge_list_json),
                "--require-real-graph",
                "--max-projection-ratio",
                str(float(args.partition_max_projection_ratio)),
                "--out",
                str(run_out),
            ]
            if bool(args.gpu_strict):
                cmd.append("--gpu-strict")
            if bool(args.allow_cpu_required):
                cmd.append("--allow-cpu-required")
            ok, sec, rc, so, se = _run(cmd)
            rpt = _load_json(run_out)
            checks = rpt.get("checks") if isinstance(rpt.get("checks"), dict) else {}
            contract_ok = bool(
                ok
                and bool(rpt.get("contract_pass", False))
                and bool(checks.get("nightly_scale_pass", False))
                and bool(checks.get("real_graph_used", False))
                and bool(checks.get("graph_source_is_real", False))
                and bool(checks.get("projection_ratio_pass", False))
                and bool(checks.get("partition_quality_threshold_pass", False))
                and (not bool(args.gpu_strict) or bool(checks.get("gpu_strict_pass", False)))
            )
            all_runs_ok = bool(all_runs_ok and contract_ok)
            report_paths.append(str(run_out))

            ten_m = None
            for row in (rpt.get("level_rows") if isinstance(rpt.get("level_rows"), list) else []):
                if isinstance(row, dict) and int(row.get("node_count", 0) or 0) == 10_000_000:
                    ten_m = row
                    break
            if ten_m is None:
                has_10m_rows = False
            else:
                lat = float(ten_m.get("projected_total_avg_branch_ms", math.nan))
                ws = float(ten_m.get("projected_total_working_set_mb", math.nan))
                if math.isfinite(lat):
                    lat_10m.append(lat)
                else:
                    has_10m_rows = False
                if math.isfinite(ws):
                    ws_10m.append(ws)
                else:
                    has_10m_rows = False

            run_rows.append(
                {
                    "run_index": i + 1,
                    "seconds": float(sec),
                    "return_code": int(rc),
                    "command": shlex.join(cmd),
                    "report_path": str(run_out),
                    "contract_pass": bool(contract_ok),
                    "stdout_tail": so,
                    "stderr_tail": se,
                }
            )

        lat_cov = _cov(lat_10m) if has_10m_rows else math.inf
        ws_cov = _cov(ws_10m) if has_10m_rows else math.inf
        checks = {
            "run_count_sufficient": bool(int(args.runs) >= 2),
            "all_runs_pass": bool(all_runs_ok),
            "has_10m_rows": bool(has_10m_rows),
            "latency_cov_pass": bool(math.isfinite(lat_cov) and lat_cov <= float(args.max_cov_latency_10m)),
            "working_set_cov_pass": bool(math.isfinite(ws_cov) and ws_cov <= float(args.max_cov_working_set_10m)),
        }
        contract_pass = bool(all(checks.values()))
        if not checks["all_runs_pass"]:
            reason_code = "ERR_RUN_FAIL"
        elif not checks["has_10m_rows"]:
            reason_code = "ERR_MISSING_10M_ROW"
        elif not (checks["latency_cov_pass"] and checks["working_set_cov_pass"]):
            reason_code = "ERR_VARIANCE_TOO_HIGH"
        elif contract_pass:
            reason_code = "PASS"
        else:
            reason_code = "ERR_VARIANCE_TOO_HIGH"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-nightly-10m-repro-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": {
                "run_count": int(args.runs),
                "latency_10m_mean_ms": statistics.fmean(lat_10m) if lat_10m else None,
                "latency_10m_cov": lat_cov if math.isfinite(lat_cov) else None,
                "working_set_10m_mean_mb": statistics.fmean(ws_10m) if ws_10m else None,
                "working_set_10m_cov": ws_cov if math.isfinite(ws_cov) else None,
            },
            "rows": run_rows,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive([str(out), *report_paths])
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote nightly 10m reproducibility report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-nightly-10m-repro-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote nightly 10m reproducibility report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
