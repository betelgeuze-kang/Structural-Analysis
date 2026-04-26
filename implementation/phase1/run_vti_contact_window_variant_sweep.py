#!/usr/bin/env python3
"""Run a small VTI contact-window variant sweep to check zero-gap-skip generality."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from runtime_contracts import InputContractError, validate_input_contract
from vti_coupled_solver import VTICoupledConfig, run_vti_coupled_solver


REASONS = {
    "PASS": "vti contact-window variant sweep completed and remained stable across variants",
    "ERR_INVALID_INPUT": "invalid vti variant sweep input",
    "ERR_VARIANT_FAIL": "one or more vti contact-window variants failed",
    "ERR_ZERO_GAP_SKIP_ABSENT": "zero-gap skip evidence did not generalize across variants",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["out"],
    "properties": {
        "out": {"type": "string", "minLength": 1},
    },
}


def _variant_row(name: str, cfg: VTICoupledConfig, irregularity_class: str, irregularity_seed: int) -> dict:
    payload = run_vti_coupled_solver(cfg, irregularity_class=irregularity_class, irregularity_seed=irregularity_seed)
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    return {
        "variant_id": name,
        "contract_pass": bool(payload.get("contract_pass", False)),
        "reason_code": str(payload.get("reason_code", "")),
        "irregularity_class": str(irregularity_class),
        "irregularity_seed": int(irregularity_seed),
        "speed_m_s": float(cfg.speed_m_s),
        "contact_window_margin_m": float(cfg.contact_window_margin_m),
        "contact_window_release_gap_m": float(cfg.contact_window_release_gap_m),
        "contact_window_force_floor_n": float(cfg.contact_window_force_floor_n),
        "retained_force_min_force_n": float(cfg.retained_force_min_force_n),
        "mean_coupling_iters": float(metrics.get("mean_coupling_iters", 0.0) or 0.0),
        "adaptive_newton_call_count": int(metrics.get("adaptive_newton_call_count", 0) or 0),
        "track_static_pruned_ratio": float(metrics.get("track_static_pruned_ratio", 0.0) or 0.0),
        "retained_force_warm_start_ratio": float(metrics.get("retained_force_warm_start_ratio", 0.0) or 0.0),
        "stable_zero_gap_skip_ratio": float(metrics.get("stable_zero_gap_skip_ratio", 0.0) or 0.0),
        "broadphase_candidate_pair_count_total": int(metrics.get("broadphase_candidate_pair_count_total", 0) or 0),
        "broadphase_rejected_pair_count_total": int(metrics.get("broadphase_rejected_pair_count_total", 0) or 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/vti_contact_window_variant_sweep_report.json")
    args = parser.parse_args()

    input_payload = {"out": str(args.out)}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_vti_contact_window_variant_sweep")

        variants = [
            _variant_row(
                "baseline_B",
                VTICoupledConfig(),
                "B",
                23,
            ),
            _variant_row(
                "sparse_A_low_speed",
                VTICoupledConfig(
                    speed_m_s=18.0,
                    contact_window_margin_m=0.55,
                    contact_window_release_gap_m=-2.5e-4,
                    contact_window_force_floor_n=180.0,
                    retained_force_min_force_n=20.0,
                ),
                "A",
                11,
            ),
            _variant_row(
                "dense_D_high_speed",
                VTICoupledConfig(
                    speed_m_s=30.0,
                    contact_window_margin_m=1.00,
                    contact_window_release_gap_m=-7.5e-4,
                    contact_window_force_floor_n=320.0,
                    retained_force_min_force_n=35.0,
                ),
                "D",
                31,
            ),
            _variant_row(
                "release_sensitive_C",
                VTICoupledConfig(
                    speed_m_s=24.0,
                    contact_window_margin_m=0.70,
                    contact_window_release_gap_m=0.0,
                    contact_window_force_floor_n=220.0,
                    retained_force_min_force_n=15.0,
                ),
                "C",
                19,
            ),
        ]

        pass_count = sum(1 for row in variants if bool(row["contract_pass"]))
        zero_gap_positive = sum(1 for row in variants if float(row["stable_zero_gap_skip_ratio"]) > 0.0)
        retained_force_positive = sum(1 for row in variants if float(row["retained_force_warm_start_ratio"]) > 0.0)
        pruned_positive = sum(1 for row in variants if float(row["track_static_pruned_ratio"]) > 0.0)

        if pass_count != len(variants):
            reason_code = "ERR_VARIANT_FAIL"
        elif zero_gap_positive < max(2, len(variants) - 1):
            reason_code = "ERR_ZERO_GAP_SKIP_ABSENT"
        else:
            reason_code = "PASS"

        summary = {
            "variant_count": int(len(variants)),
            "pass_count": int(pass_count),
            "zero_gap_positive_count": int(zero_gap_positive),
            "retained_force_positive_count": int(retained_force_positive),
            "track_static_pruned_positive_count": int(pruned_positive),
            "stable_zero_gap_skip_ratio_min": float(min(row["stable_zero_gap_skip_ratio"] for row in variants)),
            "stable_zero_gap_skip_ratio_max": float(max(row["stable_zero_gap_skip_ratio"] for row in variants)),
            "track_static_pruned_ratio_min": float(min(row["track_static_pruned_ratio"] for row in variants)),
            "track_static_pruned_ratio_max": float(max(row["track_static_pruned_ratio"] for row in variants)),
        }
        summary_line = (
            "VTI contact-window variant sweep: "
            f"{'PASS' if reason_code == 'PASS' else 'CHECK'} | "
            f"variants={len(variants)} pass={pass_count} "
            f"zero_gap={zero_gap_positive}/{len(variants)} "
            f"retained_force={retained_force_positive}/{len(variants)} "
            f"pruned={pruned_positive}/{len(variants)} "
            f"zero_gap_range={summary['stable_zero_gap_skip_ratio_min']:.2f}-{summary['stable_zero_gap_skip_ratio_max']:.2f}"
        )

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-vti-contact-window-variant-sweep",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": {
                "all_variants_pass": bool(pass_count == len(variants)),
                "zero_gap_generalized_pass": bool(zero_gap_positive >= max(2, len(variants) - 1)),
            },
            "summary": summary,
            "summary_line": summary_line,
            "variants": variants,
            "contract_pass": reason_code == "PASS",
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-vti-contact-window-variant-sweep",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(1)

    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote VTI contact-window variant sweep report: {out}")
    if not payload.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
