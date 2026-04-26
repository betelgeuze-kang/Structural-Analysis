#!/usr/bin/env python3
"""Phase-C5 tunnel longitudinal seismic deformation module."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path

import numpy as np

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract

REASONS = {
    "PASS": "tunnel longitudinal seismic response passed stability checks",
    "ERR_INVALID_INPUT": "invalid longitudinal seismic input",
    "ERR_DIVERGENCE": "longitudinal seismic integration diverged",
}

TUNNEL_SEISMIC_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "ring_count",
        "ring_spacing_m",
        "dt_s",
        "duration_s",
        "ring_mass_kg",
        "k_axial_n_m",
        "k_soil_n_m",
        "c_soil_n_s_m",
        "max_disp_m",
        "max_strain",
        "out",
    ],
    "properties": {
        "ring_count": {"type": "integer", "minimum": 10},
        "ring_spacing_m": {"type": "number", "exclusiveMinimum": 0.0},
        "dt_s": {"type": "number", "exclusiveMinimum": 0.0},
        "duration_s": {"type": "number", "exclusiveMinimum": 0.0},
        "ring_mass_kg": {"type": "number", "exclusiveMinimum": 0.0},
        "k_axial_n_m": {"type": "number", "exclusiveMinimum": 0.0},
        "k_soil_n_m": {"type": "number", "exclusiveMinimum": 0.0},
        "c_soil_n_s_m": {"type": "number", "minimum": 0.0},
        "max_disp_m": {"type": "number", "exclusiveMinimum": 0.0},
        "max_strain": {"type": "number", "exclusiveMinimum": 0.0},
        "out": {"type": "string", "minLength": 1},
    },
}


def _synthetic_ground_accel(t: float) -> float:
    return (
        0.85 * math.exp(-0.06 * t) * math.sin(2.0 * math.pi * 1.2 * t)
        + 0.35 * math.exp(-0.12 * max(0.0, t - 8.0)) * math.sin(2.0 * math.pi * 3.5 * t + 0.7)
    )


def main() -> None:
    logger = get_logger("phase1.tunnel_seismic_longitudinal")
    p = argparse.ArgumentParser()
    p.add_argument("--ring-count", type=int, default=120)
    p.add_argument("--ring-spacing-m", type=float, default=1.5)
    p.add_argument("--dt-s", type=float, default=0.002)
    p.add_argument("--duration-s", type=float, default=20.0)
    p.add_argument("--ring-mass-kg", type=float, default=9500.0)
    p.add_argument("--k-axial-n-m", type=float, default=1.1e9)
    p.add_argument("--k-soil-n-m", type=float, default=2.6e7)
    p.add_argument("--c-soil-n-s-m", type=float, default=1.2e5)
    p.add_argument("--max-disp-m", type=float, default=0.18)
    p.add_argument("--max-strain", type=float, default=0.015)
    p.add_argument("--out", default="implementation/phase1/tunnel_seismic_longitudinal_report.json")
    args = p.parse_args()

    try:
        input_payload = {
            "ring_count": int(args.ring_count),
            "ring_spacing_m": float(args.ring_spacing_m),
            "dt_s": float(args.dt_s),
            "duration_s": float(args.duration_s),
            "ring_mass_kg": float(args.ring_mass_kg),
            "k_axial_n_m": float(args.k_axial_n_m),
            "k_soil_n_m": float(args.k_soil_n_m),
            "c_soil_n_s_m": float(args.c_soil_n_s_m),
            "max_disp_m": float(args.max_disp_m),
            "max_strain": float(args.max_strain),
            "out": str(args.out),
        }
        validate_input_contract(
            input_payload,
            TUNNEL_SEISMIC_INPUT_SCHEMA,
            label="phase-c5.tunnel_seismic_longitudinal",
        )
        if input_payload["duration_s"] <= input_payload["dt_s"]:
            raise ValueError("duration_s must be greater than dt_s")
        log_event(logger, logging.INFO, "tunnel_seismic.start", inputs=input_payload)

        n = input_payload["ring_count"]
        dx = input_payload["ring_spacing_m"]
        dt = input_payload["dt_s"]
        dur = input_payload["duration_s"]
        m = input_payload["ring_mass_kg"]
        k_ax = input_payload["k_axial_n_m"]
        k_soil = input_payload["k_soil_n_m"]
        c_soil = input_payload["c_soil_n_s_m"]

        steps = int(round(dur / dt))
        u = np.zeros(n, dtype=np.float64)
        v = np.zeros(n, dtype=np.float64)

        max_disp = 0.0
        max_strain = 0.0
        max_res = 0.0
        trace_head: list[dict] = []

        for k in range(1, steps + 1):
            t = float(k) * dt
            ag = _synthetic_ground_accel(t) * 9.80665

            # Neumann-like free boundaries: mirrored neighbors.
            u_l = np.empty_like(u)
            u_r = np.empty_like(u)
            u_l[0] = u[1]
            u_l[1:] = u[:-1]
            u_r[-1] = u[-2]
            u_r[:-1] = u[1:]

            axial_term = k_ax * (u_l - 2.0 * u + u_r)
            soil_term = -k_soil * u
            damp_term = -c_soil * v
            inertia_base = -m * ag

            a = (axial_term + soil_term + damp_term + inertia_base) / m

            v = v + a * dt
            u = u + v * dt

            # Residual of semi-discrete equation.
            res = m * a - (axial_term + soil_term + damp_term + inertia_base)

            max_disp = max(max_disp, float(np.max(np.abs(u))))
            strain = np.abs(np.diff(u) / max(dx, 1e-12))
            if strain.size > 0:
                max_strain = max(max_strain, float(np.max(strain)))
            max_res = max(max_res, float(np.max(np.abs(res))))

            if k <= 200:
                trace_head.append(
                    {
                        "step": int(k),
                        "time_s": t,
                        "max_disp_m": float(np.max(np.abs(u))),
                        "max_strain": float(np.max(strain) if strain.size else 0.0),
                        "max_residual": float(np.max(np.abs(res))),
                    }
                )

        finite_ok = bool(np.isfinite(max_disp) and np.isfinite(max_strain) and np.isfinite(max_res))
        disp_ok = bool(max_disp <= float(args.max_disp_m))
        strain_ok = bool(max_strain <= float(args.max_strain))

        if finite_ok and disp_ok and strain_ok:
            reason_code = "PASS"
        else:
            reason_code = "ERR_DIVERGENCE"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-tunnel-seismic-longitudinal",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "ring_count": n,
                "ring_spacing_m": dx,
                "dt_s": dt,
                "duration_s": dur,
                "ring_mass_kg": m,
                "k_axial_n_m": k_ax,
                "k_soil_n_m": k_soil,
                "c_soil_n_s_m": c_soil,
            },
            "checks": {
                "finite_response": finite_ok,
                "displacement_limit_pass": disp_ok,
                "strain_limit_pass": strain_ok,
            },
            "metrics": {
                "max_disp_m": float(max_disp),
                "max_longitudinal_strain": float(max_strain),
                "max_equation_residual": float(max_res),
                "step_count": int(steps),
            },
            "trace_head": trace_head,
            "contract_pass": reason_code == "PASS",
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        log_event(
            logger,
            logging.INFO,
            "tunnel_seismic.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=str(payload.get("reason_code", "")),
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "tunnel_seismic.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-tunnel-seismic-longitudinal",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "tunnel_seismic.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-tunnel-seismic-longitudinal",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote tunnel seismic longitudinal report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
