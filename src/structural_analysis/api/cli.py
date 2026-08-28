"""Command line entry point for the Phase 1 core API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from structural_analysis.api._output_integrity import (
    OutputPathValidationError,
    resolve_distinct_output_paths,
    write_json_pair,
)
from structural_analysis.api.core import AnalysisConfig, analyze, load_model
from structural_analysis.generated_capabilities import (
    CAPABILITY_AUTHORITY_RULES,
    CAPABILITY_SCHEMA_VERSION,
    CURRENT_STATE_AUTHORITY,
    capabilities,
)
from structural_analysis.results.validation import validate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="structural-analysis")
    parser.add_argument(
        "model_path",
        nargs="?",
        help="IFC, MGT, or neutral canonical JSON input.",
    )
    parser.add_argument(
        "--capabilities",
        action="store_true",
        help="Print the generated capability support registry and exit.",
    )
    parser.add_argument(
        "--public-only",
        action="store_true",
        help="With --capabilities, include only public supported rows.",
    )
    parser.add_argument("--analysis-type", default="model_health")
    parser.add_argument("--solver", default="developer_preview_model_health")
    parser.add_argument("--tolerance", type=float, default=1.0e-8)
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument("--mode-count", type=int, default=6)
    parser.add_argument("--load-case")
    parser.add_argument("--reference")
    parser.add_argument(
        "--matrix-backend",
        default="numpy_linalg_solve_dense",
        choices=["numpy_linalg_solve_dense", "scipy_sparse_spsolve_cpu"],
    )
    parser.add_argument(
        "--eigen-backend",
        default="scipy_linalg_eigh_dense",
        choices=["scipy_linalg_eigh_dense"],
    )
    parser.add_argument("--out", help="Path for the analysis result JSON.")
    parser.add_argument("--report-out", help="Path for validation report JSON.")
    args = parser.parse_args(argv)

    if args.capabilities:
        print(
            json.dumps(
                {
                    "schema_version": CAPABILITY_SCHEMA_VERSION,
                    "authority_rules": CAPABILITY_AUTHORITY_RULES,
                    "current_state_authority": CURRENT_STATE_AUTHORITY,
                    "capabilities": capabilities(public_only=args.public_only),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.public_only:
        parser.error("--public-only requires --capabilities")
    if args.model_path is None:
        parser.error("model_path is required unless --capabilities is used")
    if args.out is None:
        parser.error("--out is required unless --capabilities is used")
    if args.report_out is None:
        parser.error("--report-out is required unless --capabilities is used")

    protected_paths = {"model input": Path(args.model_path)}
    if args.reference is not None:
        protected_paths["reference input"] = Path(args.reference)

    try:
        result_path, report_path = resolve_distinct_output_paths(
            Path(args.out),
            Path(args.report_out),
            protected_paths=protected_paths,
        )
    except OutputPathValidationError as error:
        parser.error(str(error))

    model = load_model(args.model_path)
    config = AnalysisConfig(
        analysis_type=args.analysis_type,
        solver=args.solver,
        tolerance=args.tolerance,
        max_iterations=args.max_iterations,
        load_case=args.load_case,
        reference=args.reference,
        matrix_backend=args.matrix_backend,
        mode_count=args.mode_count,
        eigen_backend=args.eigen_backend,
    )
    result = analyze(model, config)
    report = validate(result, args.reference)

    write_json_pair(
        result_path,
        result.to_dict(),
        report_path,
        report.to_dict(),
    )
    return 0 if report.contract_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
