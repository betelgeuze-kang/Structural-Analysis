#!/usr/bin/env python3
"""Run Phase-D multi-domain residual learning modules (D1~D4)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shlex
import subprocess
import sys
import time

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "all phase-d modules passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_MODULE_FAIL": "one or more phase-d modules failed",
}

PHASED_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["out", "max_cases", "epochs", "hidden_dim", "lr", "seed", "device"],
    "properties": {
        "out": {"type": "string", "minLength": 1},
        "max_cases": {"type": "integer", "minimum": 1},
        "epochs": {"type": "integer", "minimum": 1},
        "hidden_dim": {"type": "integer", "minimum": 1},
        "lr": {"type": "number", "exclusiveMinimum": 0.0},
        "seed": {"type": "integer"},
        "device": {"type": "string", "enum": ["auto", "cuda", "cpu"]},
        "allow_cpu_required": {"type": "boolean"},
        "max_val_mae_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "max_val_mae_pct_track": {"type": "number", "exclusiveMinimum": 0.0},
        "max_val_mae_pct_tunnel": {"type": "number", "exclusiveMinimum": 0.0},
        "max_val_rollout_mae_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "enable_p95_gate": {"type": "boolean"},
        "max_val_mae_p95_pct": {"type": "number", "exclusiveMinimum": 0.0},
        "max_val_mae_p95_pct_track": {"type": "number", "exclusiveMinimum": 0.0},
        "max_val_mae_p95_pct_tunnel": {"type": "number", "exclusiveMinimum": 0.0},
        "enable_noise_augmentation": {"type": "boolean"},
        "train_sensor_noise_pct": {"type": "number", "minimum": 0.0},
        "train_stiffness_noise_pct": {"type": "number", "minimum": 0.0},
        "robust_tail_q": {"type": "number", "minimum": 0.0, "maximum": 0.999},
        "robust_tail_weight": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "track_cases": {"type": "integer", "minimum": 1},
        "tunnel_cases": {"type": "integer", "minimum": 1},
    },
}


def _run(step: str, cmd: list[str], logs: list[dict]) -> bool:
    t0 = time.time()
    proc = subprocess.run(cmd, text=True, capture_output=True)
    logs.append(
        {
            "step": step,
            "seconds": time.time() - t0,
            "command": shlex.join(cmd),
            "return_code": int(proc.returncode),
            "stdout_tail": (proc.stdout or "")[-1200:],
            "stderr_tail": (proc.stderr or "")[-1200:],
        }
    )
    return proc.returncode == 0


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    logger = get_logger("phase1.run_phased_multidomain_modules")
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/phased_multidomain_summary_report.json")
    p.add_argument("--d1-out", default="implementation/phase1/track_dynamics_dataset_report.json")
    p.add_argument("--d2-out", default="implementation/phase1/tunnel_dynamics_dataset_report.json")
    p.add_argument("--d3-out", default="implementation/phase1/tgnn_multidomain_report.json")
    p.add_argument("--d4-out", default="implementation/phase1/moving_load_attention_report.json")
    p.add_argument("--track-dataset", default="implementation/phase1/spatiotemporal_data/track_dynamic_cases.jsonl")
    p.add_argument("--tunnel-dataset", default="implementation/phase1/spatiotemporal_data/tunnel_dynamic_cases.jsonl")
    p.add_argument("--building-dataset", default="implementation/phase1/spatiotemporal_data/dynamic_cases.jsonl")
    p.add_argument("--ckpt", default="implementation/phase1/spatiotemporal_data/tgnn_multidomain.pt")
    p.add_argument("--max-cases", type=int, default=600)
    p.add_argument("--epochs", type=int, default=12)
    p.add_argument("--hidden-dim", type=int, default=64)
    p.add_argument("--lr", type=float, default=8e-4)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    p.add_argument("--allow-cpu-required", action="store_true")
    p.add_argument("--max-val-mae-pct", type=float, default=5.0)
    p.add_argument("--max-val-mae-pct-track", type=float, default=5.0)
    p.add_argument("--max-val-mae-pct-tunnel", type=float, default=5.0)
    p.add_argument("--max-val-rollout-mae-pct", type=float, default=5.0)
    p.add_argument("--enable-p95-gate", action="store_true")
    p.add_argument("--max-val-mae-p95-pct", type=float, default=12.0)
    p.add_argument("--max-val-mae-p95-pct-track", type=float, default=15.0)
    p.add_argument("--max-val-mae-p95-pct-tunnel", type=float, default=15.0)
    p.add_argument("--enable-noise-augmentation", action="store_true")
    p.add_argument("--train-sensor-noise-pct", type=float, default=1.0)
    p.add_argument("--train-stiffness-noise-pct", type=float, default=5.0)
    p.add_argument("--robust-tail-q", type=float, default=0.95)
    p.add_argument("--robust-tail-weight", type=float, default=0.25)
    p.add_argument("--track-cases", type=int, default=420)
    p.add_argument("--tunnel-cases", type=int, default=420)
    args = p.parse_args()

    input_payload = {
        "out": str(args.out),
        "max_cases": int(args.max_cases),
        "epochs": int(args.epochs),
        "hidden_dim": int(args.hidden_dim),
        "lr": float(args.lr),
        "seed": int(args.seed),
        "device": str(args.device),
        "allow_cpu_required": bool(args.allow_cpu_required),
        "max_val_mae_pct": float(args.max_val_mae_pct),
        "max_val_mae_pct_track": float(args.max_val_mae_pct_track),
        "max_val_mae_pct_tunnel": float(args.max_val_mae_pct_tunnel),
        "max_val_rollout_mae_pct": float(args.max_val_rollout_mae_pct),
        "enable_p95_gate": bool(args.enable_p95_gate),
        "max_val_mae_p95_pct": float(args.max_val_mae_p95_pct),
        "max_val_mae_p95_pct_track": float(args.max_val_mae_p95_pct_track),
        "max_val_mae_p95_pct_tunnel": float(args.max_val_mae_p95_pct_tunnel),
        "enable_noise_augmentation": bool(args.enable_noise_augmentation),
        "train_sensor_noise_pct": float(args.train_sensor_noise_pct),
        "train_stiffness_noise_pct": float(args.train_stiffness_noise_pct),
        "robust_tail_q": float(args.robust_tail_q),
        "robust_tail_weight": float(args.robust_tail_weight),
        "track_cases": int(args.track_cases),
        "tunnel_cases": int(args.tunnel_cases),
    }

    steps: list[dict] = []
    try:
        validate_input_contract(input_payload, PHASED_INPUT_SCHEMA, label="phase-d.run_phased_multidomain_modules")
        log_event(logger, logging.INFO, "phased.start", inputs=input_payload)

        building_path = Path(args.building_dataset)
        if not building_path.exists():
            _run(
                "prepare_building_dataset",
                [
                    sys.executable,
                    "implementation/phase1/generate_spatiotemporal_bigdata.py",
                    "--dataset-out",
                    str(args.building_dataset),
                    "--report-out",
                    "implementation/phase1/spatiotemporal_data/bigdata_generation_report.json",
                    "--base-cases",
                    "420",
                    "--active-rounds",
                    "2",
                    "--hard-topk",
                    "80",
                    "--seq-len",
                    "120",
                    "--seed",
                    str(args.seed),
                ],
                steps,
            )

        ok_d1 = _run(
            "D1_generate_track_dynamics_dataset",
            [
                sys.executable,
                "implementation/phase1/generate_track_dynamics_dataset.py",
                "--out-dataset",
                str(args.track_dataset),
                "--out",
                str(args.d1_out),
                "--cases",
                str(args.track_cases),
                "--seed",
                str(args.seed),
            ],
            steps,
        )

        ok_d2 = _run(
            "D2_generate_tunnel_dynamics_dataset",
            [
                sys.executable,
                "implementation/phase1/generate_tunnel_dynamics_dataset.py",
                "--out-dataset",
                str(args.tunnel_dataset),
                "--out",
                str(args.d2_out),
                "--cases",
                str(args.tunnel_cases),
                "--seed",
                str(int(args.seed) + 11),
            ],
            steps,
        )

        ok_d4 = _run(
            "D4_moving_load_attention",
            [
                sys.executable,
                "implementation/phase1/moving_load_attention.py",
                "--out",
                str(args.d4_out),
            ],
            steps,
        )

        ok_d3 = _run(
            "D3_train_tgnn_multidomain",
            [
                sys.executable,
                "implementation/phase1/train_tgnn_baseline.py",
                "--dataset",
                str(args.building_dataset),
                "--track-dataset",
                str(args.track_dataset),
                "--tunnel-dataset",
                str(args.tunnel_dataset),
                "--max-cases",
                str(args.max_cases),
                "--epochs",
                str(args.epochs),
                "--hidden-dim",
                str(args.hidden_dim),
                "--lr",
                str(args.lr),
                "--max-val-mae-pct",
                str(args.max_val_mae_pct),
                "--max-val-mae-pct-track",
                str(args.max_val_mae_pct_track),
                "--max-val-mae-pct-tunnel",
                str(args.max_val_mae_pct_tunnel),
                "--max-val-rollout-mae-pct",
                str(args.max_val_rollout_mae_pct),
                *(["--enable-p95-gate"] if bool(args.enable_p95_gate) else []),
                "--max-val-mae-p95-pct",
                str(args.max_val_mae_p95_pct),
                "--max-val-mae-p95-pct-track",
                str(args.max_val_mae_p95_pct_track),
                "--max-val-mae-p95-pct-tunnel",
                str(args.max_val_mae_p95_pct_tunnel),
                *(["--enable-noise-augmentation"] if bool(args.enable_noise_augmentation) else []),
                "--train-sensor-noise-pct",
                str(args.train_sensor_noise_pct),
                "--train-stiffness-noise-pct",
                str(args.train_stiffness_noise_pct),
                "--robust-tail-q",
                str(args.robust_tail_q),
                "--robust-tail-weight",
                str(args.robust_tail_weight),
                "--use-moving-load-attention",
                "--attention-gain",
                "0.4",
                "--seed",
                str(args.seed),
                "--device",
                str(args.device),
                *(["--allow-cpu-required"] if bool(args.allow_cpu_required) else []),
                "--out",
                str(args.d3_out),
                "--ckpt",
                str(args.ckpt),
            ],
            steps,
        )

        r1 = _load_json(str(args.d1_out))
        r2 = _load_json(str(args.d2_out))
        r3 = _load_json(str(args.d3_out))
        r4 = _load_json(str(args.d4_out))

        checks = {
            "D1_generate_track_dynamics_dataset": bool(ok_d1 and r1.get("contract_pass", False)),
            "D2_generate_tunnel_dynamics_dataset": bool(ok_d2 and r2.get("contract_pass", False)),
            "D3_train_tgnn_multidomain": bool(ok_d3 and r3.get("contract_pass", False)),
            "D4_moving_load_attention": bool(ok_d4 and r4.get("contract_pass", False)),
        }
        all_pass = all(checks.values())
        reason_code = "PASS" if all_pass else "ERR_MODULE_FAIL"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-phased-multidomain-modules",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
            "reports": {
                "D1": str(args.d1_out),
                "D2": str(args.d2_out),
                "D3": str(args.d3_out),
                "D4": str(args.d4_out),
                "track_dataset": str(args.track_dataset),
                "tunnel_dataset": str(args.tunnel_dataset),
                "building_dataset": str(args.building_dataset),
                "ckpt": str(args.ckpt),
            },
            "steps": steps,
            "contract_pass": bool(all_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(
            logger,
            logging.INFO,
            "phased.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=reason_code,
        )
        print(f"Wrote phase-d multidomain summary report: {out}")
        if not all_pass:
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "phased.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-phased-multidomain-modules",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote phase-d multidomain summary report: {out}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "phased.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-phased-multidomain-modules",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote phase-d multidomain summary report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
