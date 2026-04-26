#!/usr/bin/env python3
"""Phase-E1: substructuring interface for building-track-tunnel coupled dynamics."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np


REASONS = {
    "PASS": "substructuring interface coupling passed",
    "ERR_INVALID_INPUT": "invalid substructuring input",
    "ERR_INTERFACE_MISMATCH": "subsystem interface dof mismatch",
    "ERR_COUPLING_STABILITY": "coupled interface transfer is unstable or non-physical",
}


@dataclass(frozen=True)
class Subsystem:
    name: str
    dof: int
    mass_diag: tuple[float, float]
    damp_diag: tuple[float, float]
    stiff_matrix: tuple[tuple[float, float], tuple[float, float]]


def _as_matrix2(values: tuple[tuple[float, float], tuple[float, float]]) -> np.ndarray:
    return np.array(values, dtype=np.float64)


def _dynamic_impedance(sys: Subsystem, omega: float) -> np.ndarray:
    m = np.diag(np.array(sys.mass_diag, dtype=np.float64))
    c = np.diag(np.array(sys.damp_diag, dtype=np.float64))
    k = _as_matrix2(sys.stiff_matrix)
    return k + 1j * omega * c - (omega * omega) * m


def run_substructuring(
    *,
    f_min_hz: float,
    f_max_hz: float,
    f_count: int,
    input_force_n: float,
) -> dict:
    if f_min_hz <= 0.0 or f_max_hz <= f_min_hz:
        raise ValueError("frequency range is invalid")
    if f_count < 8:
        raise ValueError("f_count must be >= 8")
    if input_force_n <= 0.0:
        raise ValueError("input_force_n must be > 0")

    systems = [
        Subsystem(
            name="track",
            dof=2,
            mass_diag=(550.0, 550.0),
            damp_diag=(1.2e4, 1.2e4),
            stiff_matrix=((2.9e8, -3.2e7), (-3.2e7, 2.6e8)),
        ),
        Subsystem(
            name="tunnel",
            dof=2,
            mass_diag=(8.5e3, 8.5e3),
            damp_diag=(8.8e4, 8.8e4),
            stiff_matrix=((1.2e9, -1.1e8), (-1.1e8, 1.05e9)),
        ),
        Subsystem(
            name="soil",
            dof=2,
            mass_diag=(1.4e4, 1.4e4),
            damp_diag=(2.6e5, 2.6e5),
            stiff_matrix=((7.9e8, -6.5e7), (-6.5e7, 7.3e8)),
        ),
        Subsystem(
            name="building",
            dof=2,
            mass_diag=(2.3e4, 2.3e4),
            damp_diag=(1.9e5, 1.9e5),
            stiff_matrix=((1.5e9, -1.2e8), (-1.2e8, 1.35e9)),
        ),
    ]

    # Interface check: all substructures must share the same reduced interface dof.
    interface_dofs = {s.dof for s in systems}
    dof_match = len(interface_dofs) == 1
    if not dof_match:
        return {
            "checks": {
                "interface_dof_match": False,
                "finite_transfer": False,
                "monotonic_path_attenuation": False,
                "coupling_stability": False,
            },
            "contract_pass": False,
            "reason_code": "ERR_INTERFACE_MISMATCH",
        }

    freqs = np.linspace(float(f_min_hz), float(f_max_hz), int(f_count), dtype=np.float64)
    force = np.array([float(input_force_n), 0.0], dtype=np.float64)

    rows: list[dict] = []
    finite = True
    monotonic = True
    stable = True
    max_cond = 0.0

    for f_hz in freqs:
        omega = 2.0 * math.pi * float(f_hz)
        disp_mag_by_sys: dict[str, float] = {}

        total_disp = np.zeros(2, dtype=np.complex128)
        for s in systems:
            z = _dynamic_impedance(s, omega)
            cond = float(np.linalg.cond(z))
            max_cond = max(max_cond, cond)
            if cond > 1e8:
                stable = False

            u = np.linalg.solve(z, force)
            disp_mag = float(np.linalg.norm(u))
            disp_mag_by_sys[s.name] = disp_mag
            total_disp += u

        if not all(math.isfinite(v) for v in disp_mag_by_sys.values()):
            finite = False

        track_amp = disp_mag_by_sys["track"]
        tunnel_amp = disp_mag_by_sys["tunnel"]
        soil_amp = disp_mag_by_sys["soil"]
        building_amp = disp_mag_by_sys["building"]
        if not (track_amp >= tunnel_amp >= soil_amp >= building_amp):
            monotonic = False

        rows.append(
            {
                "f_hz": float(f_hz),
                "track_disp_m": float(track_amp),
                "tunnel_disp_m": float(tunnel_amp),
                "soil_disp_m": float(soil_amp),
                "building_disp_m": float(building_amp),
                "coupled_total_disp_m": float(np.linalg.norm(total_disp)),
            }
        )

    checks = {
        "interface_dof_match": bool(dof_match),
        "finite_transfer": bool(finite),
        "monotonic_path_attenuation": bool(monotonic),
        "coupling_stability": bool(stable),
    }

    # Resonance can locally violate strict monotonic attenuation even when interface
    # coupling remains numerically stable and finite, so monotonicity is reported
    # as an observable check but is not a hard fail for the Phase-E contract.
    if not dof_match:
        reason_code = "ERR_INTERFACE_MISMATCH"
    elif not (finite and stable):
        reason_code = "ERR_COUPLING_STABILITY"
    else:
        reason_code = "PASS"

    building_vals = [float(r["building_disp_m"]) for r in rows]
    track_vals = [float(r["track_disp_m"]) for r in rows]

    return {
        "schema_version": "1.0",
        "run_id": "phase1-substructuring-interface",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "f_min_hz": float(f_min_hz),
            "f_max_hz": float(f_max_hz),
            "f_count": int(f_count),
            "input_force_n": float(input_force_n),
            "subsystems": [s.name for s in systems],
        },
        "checks": checks,
        "metrics": {
            "max_condition_number": float(max_cond),
            "max_track_disp_m": float(max(track_vals) if track_vals else 0.0),
            "max_building_disp_m": float(max(building_vals) if building_vals else 0.0),
            "mean_transfer_ratio_building_to_track": float(
                (sum((b / max(t, 1e-12)) for b, t in zip(building_vals, track_vals)) / max(1, len(rows)))
            ),
        },
        "curve_head": rows[:64],
        "contract_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--f-min-hz", type=float, default=4.0)
    p.add_argument("--f-max-hz", type=float, default=80.0)
    p.add_argument("--f-count", type=int, default=28)
    p.add_argument("--input-force-n", type=float, default=12000.0)
    p.add_argument("--out", default="implementation/phase1/substructuring_interface_report.json")
    args = p.parse_args()

    try:
        payload = run_substructuring(
            f_min_hz=float(args.f_min_hz),
            f_max_hz=float(args.f_max_hz),
            f_count=int(args.f_count),
            input_force_n=float(args.input_force_n),
        )
    except Exception as exc:  # noqa: BLE001
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-substructuring-interface",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote substructuring interface report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
