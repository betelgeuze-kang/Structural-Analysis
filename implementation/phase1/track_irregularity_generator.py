#!/usr/bin/env python3
"""Phase-B4 track irregularity generator (PSD-based spectral synthesis)."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path

import numpy as np
import torch

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract

REASONS = {
    "PASS": "track irregularity profile generated successfully",
    "ERR_INVALID_INPUT": "invalid geometry/psd input",
}

IRREGULARITY_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "length_m",
        "dx_m",
        "quality_class",
        "n0_cpm",
        "high_cut_cpm",
        "seed",
        "out_csv",
        "out",
    ],
    "properties": {
        "length_m": {"type": "number", "exclusiveMinimum": 0.0},
        "dx_m": {"type": "number", "exclusiveMinimum": 0.0},
        "quality_class": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "n0_cpm": {"type": "number", "exclusiveMinimum": 0.0},
        "high_cut_cpm": {"type": "number", "exclusiveMinimum": 0.0},
        "seed": {"type": "integer"},
        "out_csv": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


PSD_CLASS_A = {
    "A": 2.0e-8,
    "B": 8.0e-8,
    "C": 2.5e-7,
    "D": 8.0e-7,
}


@dataclass
class IrregularityConfig:
    length_m: float = 200.0
    dx_m: float = 0.05
    quality_class: str = "B"
    n0_cpm: float = 0.1
    high_cut_cpm: float = 8.0
    seed: int = 23


def _validate(cfg: IrregularityConfig) -> None:
    if cfg.length_m <= 0.0:
        raise ValueError("length_m must be > 0")
    if cfg.dx_m <= 0.0 or cfg.dx_m >= cfg.length_m:
        raise ValueError("dx_m must be > 0 and < length_m")
    if cfg.quality_class not in PSD_CLASS_A:
        raise ValueError(f"quality_class must be one of {sorted(PSD_CLASS_A)}")
    if cfg.n0_cpm <= 0.0:
        raise ValueError("n0_cpm must be > 0")
    if cfg.high_cut_cpm <= cfg.n0_cpm:
        raise ValueError("high_cut_cpm must be > n0_cpm")


def _psd_profile(n_cpm: np.ndarray, quality_class: str, n0_cpm: float) -> np.ndarray:
    # Canonical rail roughness-like PSD shape: S(n) = A*(n0^2)/(n^2+n0^2)
    # Unit: m^3 / cycle-per-meter
    a = float(PSD_CLASS_A[quality_class])
    n2 = n_cpm * n_cpm
    n0_2 = float(n0_cpm) * float(n0_cpm)
    return a * n0_2 / np.maximum(n2 + n0_2, 1e-12)


def _gpu_preprocess_enabled() -> bool:
    return os.environ.get("PHASE1_GPU_PREPROCESS", "0") == "1" or os.environ.get(
        "PHASE1_GPU_PREPROCESS_STRICT", "0"
    ) == "1"


def _rocm_device() -> str | None:
    try:
        if torch.cuda.is_available():
            return "cuda"
    except Exception:  # noqa: BLE001
        return None
    return None


def generate_profile(cfg: IrregularityConfig) -> tuple[np.ndarray, np.ndarray, dict]:
    _validate(cfg)
    n_nodes = int(round(cfg.length_m / cfg.dx_m)) + 1
    x = np.linspace(0.0, float(cfg.length_m), n_nodes, dtype=np.float64)

    preprocess_backend = "numpy_cpu"
    device = _rocm_device() if _gpu_preprocess_enabled() else None
    if device:
        preprocess_backend = "rocm_torch_full"
        freq_count = (n_nodes // 2) + 1
        freqs_t = torch.arange(freq_count, device=device, dtype=torch.float64) / (float(n_nodes) * float(cfg.dx_m))
        if int(freqs_t.numel()) < 3:
            raise ValueError("insufficient frequency bins")
        n0_sq = float(cfg.n0_cpm) * float(cfg.n0_cpm)
        psd_t = float(PSD_CLASS_A[cfg.quality_class]) * n0_sq / torch.clamp(freqs_t * freqs_t + n0_sq, min=1.0e-12)
        psd_t[0] = 0.0
        psd_t = torch.where(
            freqs_t > float(cfg.high_cut_cpm),
            torch.zeros_like(psd_t),
            psd_t,
        )
        df = float((freqs_t[1] - freqs_t[0]).item())
        amp_t = torch.sqrt(2.0 * torch.clamp(psd_t, min=0.0) * max(df, 1.0e-12))
        phase_gen = torch.Generator(device=device)
        phase_gen.manual_seed(int(cfg.seed))
        phase_t = torch.rand(freqs_t.shape, generator=phase_gen, device=device, dtype=torch.float64) * (2.0 * math.pi)
        x_t = torch.linspace(0.0, float(cfg.length_m), n_nodes, device=device, dtype=torch.float64)
        cos_terms = torch.cos(
            (2.0 * math.pi) * freqs_t.unsqueeze(1) * x_t.unsqueeze(0) + phase_t.unsqueeze(1)
        )
        z_t = torch.sum(amp_t.unsqueeze(1) * cos_terms, dim=0)
        z_t = z_t - torch.mean(z_t)
        freqs = freqs_t.detach().cpu().numpy()
        z = z_t.detach().cpu().numpy()
    else:
        # Positive-frequency bins for real-valued synthesis.
        freqs = np.fft.rfftfreq(n_nodes, d=float(cfg.dx_m))  # cycles/m
        if len(freqs) < 3:
            raise ValueError("insufficient frequency bins")

        psd = _psd_profile(freqs, cfg.quality_class, cfg.n0_cpm)
        psd[0] = 0.0
        psd[freqs > float(cfg.high_cut_cpm)] = 0.0

        df = freqs[1] - freqs[0]
        amp = np.sqrt(2.0 * np.maximum(psd, 0.0) * max(df, 1e-12))

        rng = np.random.default_rng(int(cfg.seed))
        phase = rng.uniform(0.0, 2.0 * math.pi, size=freqs.shape)
        coeff = amp * np.exp(1j * phase)
        coeff[0] = 0.0
        if n_nodes % 2 == 0:
            coeff[-1] = coeff[-1].real + 0.0j

        z = np.fft.irfft(coeff, n=n_nodes)
        z = z - float(np.mean(z))

    # Report roughness metrics.
    rms = float(np.sqrt(np.mean(z * z)))
    p95 = float(np.percentile(np.abs(z), 95.0))
    peak = float(np.max(np.abs(z)))

    metrics = {
        "node_count": int(n_nodes),
        "dx_m": float(cfg.dx_m),
        "length_m": float(cfg.length_m),
        "rms_m": rms,
        "p95_abs_m": p95,
        "peak_abs_m": peak,
        "class": cfg.quality_class,
        "seed": int(cfg.seed),
        "n0_cpm": float(cfg.n0_cpm),
        "high_cut_cpm": float(cfg.high_cut_cpm),
        "preprocess_backend": preprocess_backend,
    }
    return x, z, metrics


def sample_profile_at(x: np.ndarray, z: np.ndarray, x_query_m: float) -> float:
    if len(x) == 0:
        return 0.0
    xq = max(float(x[0]), min(float(x[-1]), float(x_query_m)))
    return float(np.interp(xq, x, z))


def _write_csv(path: Path, x: np.ndarray, z: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["x_m", "z_m"])
        for xi, zi in zip(x, z):
            w.writerow([f"{float(xi):.6f}", f"{float(zi):.12e}"])


def main() -> None:
    logger = get_logger("phase1.track_irregularity_generator")
    p = argparse.ArgumentParser()
    p.add_argument("--length-m", type=float, default=200.0)
    p.add_argument("--dx-m", type=float, default=0.05)
    p.add_argument("--quality-class", default="B", choices=sorted(PSD_CLASS_A))
    p.add_argument("--n0-cpm", type=float, default=0.1)
    p.add_argument("--high-cut-cpm", type=float, default=8.0)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--out-csv", default="implementation/phase1/open_data/track/irregularity_profile.csv")
    p.add_argument("--out", default="implementation/phase1/track_irregularity_report.json")
    args = p.parse_args()

    try:
        input_payload = {
            "length_m": float(args.length_m),
            "dx_m": float(args.dx_m),
            "quality_class": str(args.quality_class),
            "n0_cpm": float(args.n0_cpm),
            "high_cut_cpm": float(args.high_cut_cpm),
            "seed": int(args.seed),
            "out_csv": str(args.out_csv),
            "out": str(args.out),
        }
        validate_input_contract(
            input_payload,
            IRREGULARITY_INPUT_SCHEMA,
            label="phase-b4.track_irregularity_generator",
        )
        log_event(logger, logging.INFO, "track_irregularity.start", inputs=input_payload)
        cfg = IrregularityConfig(
            length_m=float(args.length_m),
            dx_m=float(args.dx_m),
            quality_class=str(args.quality_class),
            n0_cpm=float(args.n0_cpm),
            high_cut_cpm=float(args.high_cut_cpm),
            seed=int(args.seed),
        )
        x, z, metrics = generate_profile(cfg)
        _write_csv(Path(args.out_csv), x, z)
        reason_code = "PASS"
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-track-irregularity-generator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": True,
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
            "inputs": {
                "length_m": cfg.length_m,
                "dx_m": cfg.dx_m,
                "quality_class": cfg.quality_class,
                "n0_cpm": cfg.n0_cpm,
                "high_cut_cpm": cfg.high_cut_cpm,
                "seed": cfg.seed,
            },
            "outputs": {
                "profile_csv": str(args.out_csv),
            },
            "metrics": metrics,
            "sample_head": [
                {"x_m": float(x[i]), "z_m": float(z[i])}
                for i in range(min(16, len(x)))
            ],
        }
        log_event(
            logger,
            logging.INFO,
            "track_irregularity.completed",
            contract_pass=bool(payload.get("contract_pass", False)),
            reason_code=str(payload.get("reason_code", "")),
        )
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "track_irregularity.invalid_input", error=str(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-track-irregularity-generator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote track irregularity report: {out}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "track_irregularity.internal_error", error=repr(exc))
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-track-irregularity-generator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote track irregularity report: {out}")
        raise SystemExit(1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote track irregularity report: {out}")


if __name__ == "__main__":
    main()
