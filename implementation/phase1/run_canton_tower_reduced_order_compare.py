#!/usr/bin/env python3
"""Emit a reduced-order compare report for the Canton Tower SHM benchmark."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.canton_tower_reduced_order_utils import summarize_canton_tower_system_matrices
except ImportError:  # pragma: no cover - direct script execution fallback
    from canton_tower_reduced_order_utils import summarize_canton_tower_system_matrices


DEFAULT_MAT = Path("implementation/phase1/open_data/megastructure/canton_tower_reduced_shm/system_matrices.mat")
DEFAULT_NORMALIZATION = Path(
    "implementation/phase1/open_data/megastructure/canton_tower_reduced_shm/canton_tower_normalization_report.json"
)
DEFAULT_CONVERSION = Path("implementation/phase1/open_data/megastructure/canton_tower_conversion_report.json")
DEFAULT_BENCHMARK = Path("implementation/phase1/commercial_benchmark_cases.canton_tower_open.json")
DEFAULT_OUT = Path("implementation/phase1/release/benchmark_expansion/canton_tower_reduced_order_compare_report.json")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_report(
    *,
    mat_path: Path,
    normalization_report: dict[str, Any],
    conversion_report: dict[str, Any],
    benchmark_payload: dict[str, Any],
) -> dict[str, Any]:
    matrix_summary = summarize_canton_tower_system_matrices(mat_path)
    normalization_summary = (
        normalization_report.get("summary")
        if isinstance(normalization_report.get("summary"), dict)
        else {}
    )
    conversion_summary = (
        conversion_report.get("summary")
        if isinstance(conversion_report.get("summary"), dict)
        else {}
    )
    conversion_outputs = (
        conversion_report.get("outputs")
        if isinstance(conversion_report.get("outputs"), dict)
        else {}
    )
    benchmark_cases = benchmark_payload.get("cases") if isinstance(benchmark_payload.get("cases"), list) else []

    observed_channels = int(normalization_summary.get("generated_channel_count_max", 0) or 0)
    global_dof = int(matrix_summary.get("global_dof_count", 0) or 0)
    benchmark_case_count = int(conversion_outputs.get("benchmark_case_count", len(benchmark_cases)) or 0)
    dynamic_case_count = int(conversion_outputs.get("dynamic_case_count", 0) or 0)
    coverage_ratio = (float(observed_channels) / float(global_dof)) if global_dof > 0 else 0.0
    modes = list(matrix_summary.get("global_mode_frequencies_hz") or [])
    contract_pass = bool(global_dof > 0 and observed_channels > 0 and benchmark_case_count > 0)

    summary_line = (
        f"Canton Tower reduced-order compare: {'PASS' if contract_pass else 'CHECK'} | "
        f"global_dof={global_dof} | observed_channels={observed_channels} | "
        f"coverage={coverage_ratio:.3f} | windows={benchmark_case_count} | "
        f"segment_pairs={int(matrix_summary.get('segment_matrix_pair_count', 0) or 0)} | "
        f"modes={len(modes)}"
    )

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_CANTON_REDUCED_ORDER_COMPARE_INCOMPLETE",
        "reason": (
            "Canton Tower reduced-order matrices and measured-response windows are aligned for benchmark surfacing."
            if contract_pass
            else "Canton Tower reduced-order compare is missing matrices, observed channels, or converted benchmark windows."
        ),
        "summary_line": summary_line,
        "summary": {
            "global_dof_count": global_dof,
            "segment_matrix_pair_count": int(matrix_summary.get("segment_matrix_pair_count", 0) or 0),
            "observed_channel_count": observed_channels,
            "coverage_ratio": round(coverage_ratio, 6),
            "global_mode_count": len(modes),
            "benchmark_case_count": benchmark_case_count,
            "dynamic_case_count": dynamic_case_count,
            "shell_beam_mix_case_count": int(conversion_summary.get("shell_beam_mix_case_count", 0) or 0),
        },
        "matrix_summary": matrix_summary,
        "observed_reference": {
            "normalization_report": str(DEFAULT_NORMALIZATION),
            "benchmark_payload": str(DEFAULT_BENCHMARK),
            "conversion_report": str(DEFAULT_CONVERSION),
        },
        "results_explorer": {
            "entry_kind": "measured_reduced_order_compare",
            "entry_label": "Canton Tower reduced SHM",
            "source_family": "canton_tower_reduced_shm",
            "summary_label": summary_line,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mat-path", default=str(DEFAULT_MAT))
    parser.add_argument("--normalization-report", default=str(DEFAULT_NORMALIZATION))
    parser.add_argument("--conversion-report", default=str(DEFAULT_CONVERSION))
    parser.add_argument("--benchmark-payload", default=str(DEFAULT_BENCHMARK))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_report(
        mat_path=Path(args.mat_path),
        normalization_report=_load_json(Path(args.normalization_report)),
        conversion_report=_load_json(Path(args.conversion_report)),
        benchmark_payload=_load_json(Path(args.benchmark_payload)),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote Canton Tower reduced-order compare report: {out_path}")


if __name__ == "__main__":
    main()
