#!/usr/bin/env python3
"""Phase-C3 soil-tunnel SSI impedance module (frequency-dependent spring/damper)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

import numpy as np

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract

REASONS = {
    "PASS": "soil-tunnel SSI impedance contract passed",
    "ERR_INVALID_INPUT": "invalid SSI input",
    "ERR_SSI_NUMERICS": "SSI numerical checks failed",
}

SOIL_SSI_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "soil",
        "ring_mass_kg",
        "f_min_hz",
        "f_max_hz",
        "f_count",
        "ref_hz",
        "out",
    ],
    "properties": {
        "soil": {"type": "string", "enum": ["soft_clay", "dense_sand", "weathered_rock"]},
        "ring_mass_kg": {"type": "number", "exclusiveMinimum": 0.0},
        "f_min_hz": {"type": "number", "exclusiveMinimum": 0.0},
        "f_max_hz": {"type": "number", "exclusiveMinimum": 0.0},
        "f_count": {"type": "integer", "minimum": 10},
        "ref_hz": {"type": "number", "exclusiveMinimum": 0.0},
        "out": {"type": "string", "minLength": 1},
    },
}


SOIL_PRESETS = {
    "soft_clay": {"k0": 2.4e7, "c0": 8.0e4, "stiff_exp": 0.45, "damp_slope": 0.55},
    "dense_sand": {"k0": 6.8e7, "c0": 1.6e5, "stiff_exp": 0.35, "damp_slope": 0.42},
    "weathered_rock": {"k0": 1.6e8, "c0": 2.4e5, "stiff_exp": 0.22, "damp_slope": 0.30},
}


def _impedance_curve(
    *,
    freq_hz: np.ndarray,
    k0: float,
    c0: float,
    stiff_exp: float,
    damp_slope: float,
    ref_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    fr = np.maximum(freq_hz / max(float(ref_hz), 1e-6), 1e-6)
    kf = float(k0) * (1.0 + np.power(fr, float(stiff_exp)))
    cf = float(c0) * (1.0 + float(damp_slope) * fr)
    return kf, cf


def _transfer_amp(freq_hz: np.ndarray, m: float, kf: np.ndarray, cf: np.ndarray) -> np.ndarray:
    w = 2.0 * np.pi * freq_hz
    den = np.sqrt((kf - float(m) * w * w) ** 2 + (cf * w) ** 2)
    return 1.0 / np.maximum(den, 1e-12)


def main() -> None:
    logger = get_logger("phase1.soil_tunnel_ssi")
    p = argparse.ArgumentParser()
    p.add_argument("--soil", default="dense_sand", choices=sorted(SOIL_PRESETS))
    p.add_argument("--ring-mass-kg", type=float, default=9500.0)
    p.add_argument("--f-min-hz", type=float, default=0.5)
    p.add_argument("--f-max-hz", type=float, default=30.0)
    p.add_argument("--f-count", type=int, default=180)
    p.add_argument("--ref-hz", type=float, default=5.0)
    p.add_argument("--out", default="implementation/phase1/soil_tunnel_ssi_report.json")
    args = p.parse_args()

    try:
        input_payload = {
            "soil": str(args.soil),
            "ring_mass_kg": float(args.ring_mass_kg),
            "f_min_hz": float(args.f_min_hz),
            "f_max_hz": float(args.f_max_hz),
            "f_count": int(args.f_count),
            "ref_hz": float(args.ref_hz),
            "out": str(args.out),
        }
        validate_input_contract(input_payload, SOIL_SSI_INPUT_SCHEMA, label="phase-c3.soil_tunnel_ssi")
        if input_payload["f_max_hz"] <= input_payload["f_min_hz"]:
            raise ValueError("f_max_hz must be greater than f_min_hz")
        log_event(logger, logging.INFO, "soil_ssi.start", inputs=input_payload)

        soil = SOIL_PRESETS[input_payload["soil"]]
        freq = np.linspace(
            input_payload["f_min_hz"],
            input_payload["f_max_hz"],
            input_payload["f_count"],
            dtype=np.float64,
        )
        kf, cf = _impedance_curve(
            freq_hz=freq,
            k0=float(soil["k0"]),
            c0=float(soil["c0"]),
            stiff_exp=float(soil["stiff_exp"]),
            damp_slope=float(soil["damp_slope"]),
            ref_hz=input_payload["ref_hz"],
        )
        amp = _transfer_amp(freq, input_payload["ring_mass_kg"], kf, cf)

        finite_ok = bool(np.all(np.isfinite(kf)) and np.all(np.isfinite(cf)) and np.all(np.isfinite(amp)))
        monotonic_k = bool(np.all(np.diff(kf) >= -1e-9))
        positive_damping = bool(np.all(cf > 0.0))
        attenuation_ok = bool(float(np.median(amp[-20:])) < float(np.median(amp[:20])))

        if finite_ok and monotonic_k and positive_damping and attenuation_ok:
            reason_code = "PASS"
        else:
            reason_code = "ERR_SSI_NUMERICS"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-soil-tunnel-ssi",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "soil": input_payload["soil"],
                "ring_mass_kg": input_payload["ring_mass_kg"],
                "f_min_hz": input_payload["f_min_hz"],
                "f_max_hz": input_payload["f_max_hz"],
                "f_count": input_payload["f_count"],
                "ref_hz": input_payload["ref_hz"],
                "soil_params": soil,
            },
            "checks": {
                "finite_response": finite_ok,
                "monotonic_stiffness": monotonic_k,
                "positive_damping": positive_damping,
                "high_freq_attenuation": attenuation_ok,
            },
            "metrics": {
                "k_min": float(np.min(kf)),
                "k_max": float(np.max(kf)),
                "c_min": float(np.min(cf)),
                "c_max": float(np.max(cf)),
                "amp_low_band_median": float(np.median(amp[:20])),
                "amp_high_band_median": float(np.median(amp[-20:])),
            },
            "curve_head": [
                {
                    "f_hz": float(freq[i]),
                    "k_n_m": float(kf[i]),
                    "c_n_s_m": float(cf[i]),
                    "transfer_amp": float(amp[i]),
                }
                for i in range(min(80, len(freq)))
            ],
            "contract_pass": reason_code == "PASS",
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        log_event(
            logger,
            logging.INFO,
            "soil_ssi.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=str(payload.get("reason_code", "")),
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "soil_ssi.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-soil-tunnel-ssi",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "soil_ssi.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-soil-tunnel-ssi",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote soil-tunnel SSI report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
