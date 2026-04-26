#!/usr/bin/env python3
"""Phase-C2 segment-joint nonlinear spring (LJ-like softening surrogate)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

import numpy as np

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract

REASONS = {
    "PASS": "segment-joint nonlinear response contract passed",
    "ERR_INVALID_INPUT": "invalid joint model input",
    "ERR_JOINT_NONLINEAR": "joint nonlinear response checks failed",
}

JOINT_NONLINEAR_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["k0", "theta_y", "theta_max", "soft_beta", "unload_ratio", "points", "out"],
    "properties": {
        "k0": {"type": "number", "exclusiveMinimum": 0.0},
        "theta_y": {"type": "number", "exclusiveMinimum": 0.0},
        "theta_max": {"type": "number", "exclusiveMinimum": 0.0},
        "soft_beta": {"type": "number", "exclusiveMinimum": 0.0},
        "unload_ratio": {"type": "number", "exclusiveMinimum": 0.0, "exclusiveMaximum": 1.0},
        "points": {"type": "integer", "minimum": 20},
        "out": {"type": "string", "minLength": 1},
    },
}


def _joint_moment(theta: np.ndarray, k0: float, theta_y: float, soft_beta: float, m_cap: float) -> np.ndarray:
    out = np.empty_like(theta)
    for i, t in enumerate(theta):
        tt = max(float(t), 0.0)
        if tt <= theta_y:
            m = k0 * tt
        else:
            m = k0 * theta_y * np.exp(-soft_beta * (tt - theta_y) / max(theta_y, 1e-12))
        out[i] = min(m, m_cap)
    return out


def simulate_joint_cycle(
    *,
    k0: float,
    theta_y: float,
    theta_max: float,
    soft_beta: float,
    unload_ratio: float,
    points: int,
) -> dict:
    th_up = np.linspace(0.0, float(theta_max), int(points), dtype=np.float64)
    m_cap = 1.5 * float(k0) * float(theta_y)
    m_up = _joint_moment(th_up, float(k0), float(theta_y), float(soft_beta), m_cap)

    # Unloading with reduced stiffness to create hysteretic dissipation.
    th_down = np.linspace(float(theta_max), 0.0, int(points), dtype=np.float64)
    k_unload = float(k0) * float(unload_ratio)
    m_start = float(m_up[-1])
    m_down = np.maximum(0.0, m_start + k_unload * (th_down - float(theta_max)))

    th_cycle = np.concatenate([th_up, th_down[1:]])
    m_cycle = np.concatenate([m_up, m_down[1:]])

    # Approximate enclosed hysteresis area.
    dtheta = np.diff(th_cycle)
    m_mid = 0.5 * (m_cycle[:-1] + m_cycle[1:])
    work = float(np.sum(m_mid * dtheta))
    diss = float(abs(work))

    peak_idx = int(np.argmax(m_up))
    peak_m = float(m_up[peak_idx])
    post_peak = float(np.max(m_up[peak_idx + 1 :])) if peak_idx + 1 < len(m_up) else peak_m

    checks = {
        "yield_detected": bool(peak_idx > 0),
        "post_yield_softening_pass": bool(post_peak <= 0.98 * peak_m + 1e-12),
        "energy_dissipation_pass": bool(diss > 1e-9),
    }

    return {
        "inputs": {
            "k0_n_m_per_rad": float(k0),
            "theta_y_rad": float(theta_y),
            "theta_max_rad": float(theta_max),
            "soft_beta": float(soft_beta),
            "unload_ratio": float(unload_ratio),
            "points": int(points),
        },
        "checks": checks,
        "metrics": {
            "peak_moment_n_m": peak_m,
            "post_peak_max_n_m": post_peak,
            "yield_index": peak_idx,
            "dissipated_energy_like": diss,
        },
        "curve_head": [
            {"theta_rad": float(th_cycle[i]), "moment_n_m": float(m_cycle[i])}
            for i in range(min(80, len(th_cycle)))
        ],
    }


def main() -> None:
    logger = get_logger("phase1.tunnel_segment_joint_nonlinear")
    p = argparse.ArgumentParser()
    p.add_argument("--k0", type=float, default=2.5e7)
    p.add_argument("--theta-y", type=float, default=0.004)
    p.add_argument("--theta-max", type=float, default=0.018)
    p.add_argument("--soft-beta", type=float, default=2.4)
    p.add_argument("--unload-ratio", type=float, default=0.62)
    p.add_argument("--points", type=int, default=240)
    p.add_argument("--out", default="implementation/phase1/tunnel_segment_joint_report.json")
    args = p.parse_args()

    try:
        input_payload = {
            "k0": float(args.k0),
            "theta_y": float(args.theta_y),
            "theta_max": float(args.theta_max),
            "soft_beta": float(args.soft_beta),
            "unload_ratio": float(args.unload_ratio),
            "points": int(args.points),
            "out": str(args.out),
        }
        validate_input_contract(
            input_payload,
            JOINT_NONLINEAR_INPUT_SCHEMA,
            label="phase-c2.tunnel_segment_joint_nonlinear",
        )
        if input_payload["theta_max"] <= input_payload["theta_y"]:
            raise ValueError("theta_max must be greater than theta_y")
        log_event(logger, logging.INFO, "tunnel_joint.start", inputs=input_payload)

        sim = simulate_joint_cycle(
            k0=input_payload["k0"],
            theta_y=input_payload["theta_y"],
            theta_max=input_payload["theta_max"],
            soft_beta=input_payload["soft_beta"],
            unload_ratio=input_payload["unload_ratio"],
            points=input_payload["points"],
        )

        c = sim["checks"]
        if c["yield_detected"] and c["post_yield_softening_pass"] and c["energy_dissipation_pass"]:
            reason_code = "PASS"
        else:
            reason_code = "ERR_JOINT_NONLINEAR"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-tunnel-segment-joint-nonlinear",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **sim,
            "contract_pass": reason_code == "PASS",
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        log_event(
            logger,
            logging.INFO,
            "tunnel_joint.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=str(payload.get("reason_code", "")),
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "tunnel_joint.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-tunnel-segment-joint-nonlinear",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "tunnel_joint.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-tunnel-segment-joint-nonlinear",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote tunnel segment joint report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
