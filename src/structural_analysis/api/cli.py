"""Command line entry point for the Phase 1 core API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from structural_analysis.api.core import AnalysisConfig, analyze, load_model, validate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="structural-analysis")
    parser.add_argument("model_path", help="IFC, MGT, or neutral canonical JSON input.")
    parser.add_argument("--analysis-type", default="model_health")
    parser.add_argument("--solver", default="developer_preview_model_health")
    parser.add_argument("--tolerance", type=float, default=1.0e-8)
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument("--load-case")
    parser.add_argument("--reference")
    parser.add_argument(
        "--matrix-backend",
        default="numpy_linalg_solve_dense",
        choices=["numpy_linalg_solve_dense", "scipy_sparse_spsolve_cpu"],
    )
    parser.add_argument("--out", required=True, help="Path for the analysis result JSON.")
    parser.add_argument("--report-out", required=True, help="Path for validation report JSON.")
    args = parser.parse_args(argv)

    model = load_model(args.model_path)
    config = AnalysisConfig(
        analysis_type=args.analysis_type,
        solver=args.solver,
        tolerance=args.tolerance,
        max_iterations=args.max_iterations,
        load_case=args.load_case,
        reference=args.reference,
        matrix_backend=args.matrix_backend,
    )
    result = analyze(model, config)
    report = validate(result, args.reference)

    _write_json(Path(args.out), result.to_dict())
    _write_json(Path(args.report_out), report.to_dict())
    return 0 if report.contract_pass else 2


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
