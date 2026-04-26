#!/usr/bin/env python3
"""Phase-C4 train passage load time-series generator for tunnel dynamics."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path

import numpy as np

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract

REASONS = {
    "PASS": "train passage load time-series generated",
    "ERR_INVALID_INPUT": "invalid train passage input",
}

TRAIN_PASSAGE_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "tunnel_length_m",
        "speed_m_s",
        "dt_s",
        "duration_s",
        "axle_load_n",
        "axle_spacing_m",
        "cars",
        "car_gap_m",
        "entry_offset_m",
        "pressure_peak_pa",
        "out_csv",
        "out",
    ],
    "properties": {
        "tunnel_length_m": {"type": "number", "exclusiveMinimum": 0.0},
        "speed_m_s": {"type": "number", "exclusiveMinimum": 0.0},
        "dt_s": {"type": "number", "exclusiveMinimum": 0.0},
        "duration_s": {"type": "number", "exclusiveMinimum": 0.0},
        "axle_load_n": {"type": "number", "exclusiveMinimum": 0.0},
        "axle_spacing_m": {"type": "array", "items": {"type": "number"}, "minItems": 1},
        "cars": {"type": "integer", "minimum": 1},
        "car_gap_m": {"type": "number", "exclusiveMinimum": 0.0},
        "entry_offset_m": {"type": "number"},
        "pressure_peak_pa": {"type": "number", "minimum": 0.0},
        "out_csv": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _axle_positions(
    *,
    t_s: float,
    speed_m_s: float,
    axle_offsets_m: list[float],
    entry_offset_m: float,
) -> list[float]:
    x_head = float(speed_m_s) * float(t_s) - float(entry_offset_m)
    return [x_head - float(o) for o in axle_offsets_m]


def main() -> None:
    logger = get_logger("phase1.train_passage_load_generator")
    p = argparse.ArgumentParser()
    p.add_argument("--tunnel-length-m", type=float, default=1200.0)
    p.add_argument("--speed-m-s", type=float, default=25.0)
    p.add_argument("--dt-s", type=float, default=0.01)
    p.add_argument("--duration-s", type=float, default=60.0)
    p.add_argument("--axle-load-n", type=float, default=85000.0)
    p.add_argument("--axle-spacing-m", default="2.5,2.5,2.5")
    p.add_argument("--cars", type=int, default=8)
    p.add_argument("--car-gap-m", type=float, default=12.0)
    p.add_argument("--entry-offset-m", type=float, default=80.0)
    p.add_argument("--pressure-peak-pa", type=float, default=1200.0)
    p.add_argument("--out-csv", default="implementation/phase1/open_data/tunnel/train_passage_load.csv")
    p.add_argument("--out", default="implementation/phase1/train_passage_load_report.json")
    args = p.parse_args()

    try:
        spacing = [float(x.strip()) for x in str(args.axle_spacing_m).split(",") if x.strip()]
        input_payload = {
            "tunnel_length_m": float(args.tunnel_length_m),
            "speed_m_s": float(args.speed_m_s),
            "dt_s": float(args.dt_s),
            "duration_s": float(args.duration_s),
            "axle_load_n": float(args.axle_load_n),
            "axle_spacing_m": spacing,
            "cars": int(args.cars),
            "car_gap_m": float(args.car_gap_m),
            "entry_offset_m": float(args.entry_offset_m),
            "pressure_peak_pa": float(args.pressure_peak_pa),
            "out_csv": str(args.out_csv),
            "out": str(args.out),
        }
        validate_input_contract(
            input_payload,
            TRAIN_PASSAGE_INPUT_SCHEMA,
            label="phase-c4.train_passage_load_generator",
        )
        if input_payload["duration_s"] <= input_payload["dt_s"]:
            raise ValueError("duration_s must be greater than dt_s")
        log_event(logger, logging.INFO, "train_passage.start", inputs=input_payload)

        # Build per-car axle offsets.
        axle_offsets_car = [0.0]
        for s in spacing:
            axle_offsets_car.append(axle_offsets_car[-1] + float(s))
        car_len_ref = axle_offsets_car[-1] + float(args.car_gap_m)

        axle_offsets_full: list[float] = []
        for c in range(input_payload["cars"]):
            base = float(c) * car_len_ref
            for off in axle_offsets_car:
                axle_offsets_full.append(base + off)

        steps = int(round(input_payload["duration_s"] / input_payload["dt_s"]))
        tunnel_len = input_payload["tunnel_length_m"]

        rows: list[dict] = []
        peak_load = 0.0
        peak_pressure = 0.0

        for k in range(steps + 1):
            t = float(k) * input_payload["dt_s"]
            x_axles = _axle_positions(
                t_s=t,
                speed_m_s=input_payload["speed_m_s"],
                axle_offsets_m=axle_offsets_full,
                entry_offset_m=input_payload["entry_offset_m"],
            )

            in_tunnel = [x for x in x_axles if 0.0 <= x <= tunnel_len]
            total_load = float(len(in_tunnel)) * input_payload["axle_load_n"]

            # Simple micro-pressure wave envelope: pulse at entry and exit.
            x_head = input_payload["speed_m_s"] * t - input_payload["entry_offset_m"]
            x_tail = x_head - max(axle_offsets_full)
            entry_pulse = math.exp(-((x_head - 0.0) / 45.0) ** 2)
            exit_pulse = math.exp(-((x_tail - tunnel_len) / 45.0) ** 2)
            pressure = input_payload["pressure_peak_pa"] * (entry_pulse + exit_pulse)

            peak_load = max(peak_load, total_load)
            peak_pressure = max(peak_pressure, pressure)

            rows.append(
                {
                    "time_s": t,
                    "active_axle_count": len(in_tunnel),
                    "total_vertical_load_n": total_load,
                    "micro_pressure_wave_pa": pressure,
                }
            )

        out_csv = Path(args.out_csv)
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-train-passage-load-generator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "tunnel_length_m": input_payload["tunnel_length_m"],
                "speed_m_s": input_payload["speed_m_s"],
                "dt_s": input_payload["dt_s"],
                "duration_s": input_payload["duration_s"],
                "axle_load_n": input_payload["axle_load_n"],
                "axle_spacing_m": spacing,
                "cars": input_payload["cars"],
                "car_gap_m": input_payload["car_gap_m"],
                "entry_offset_m": input_payload["entry_offset_m"],
                "pressure_peak_pa": input_payload["pressure_peak_pa"],
            },
            "outputs": {
                "csv": str(out_csv),
                "sample_count": len(rows),
            },
            "checks": {
                "nonempty": bool(len(rows) > 2),
                "peak_load_positive": bool(peak_load > 0.0),
                "peak_pressure_positive": bool(peak_pressure > 0.0),
            },
            "metrics": {
                "peak_total_vertical_load_n": peak_load,
                "peak_micro_pressure_wave_pa": peak_pressure,
                "max_active_axle_count": int(max(r["active_axle_count"] for r in rows)),
            },
            "trace_head": rows[:120],
            "contract_pass": True,
            "reason_code": "PASS",
            "reason": REASONS["PASS"],
        }
        log_event(
            logger,
            logging.INFO,
            "train_passage.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=str(payload.get("reason_code", "")),
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "train_passage.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-train-passage-load-generator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "train_passage.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-train-passage-load-generator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote train passage load report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
