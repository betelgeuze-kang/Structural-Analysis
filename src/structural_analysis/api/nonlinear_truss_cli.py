"""CLI for the bounded public canonical two-bar nonlinear truss path."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from structural_analysis.api._output_integrity import (
    OutputPathValidationError,
    resolve_distinct_output_paths,
    write_json_pair,
)
from structural_analysis.api.core import load_model
from structural_analysis.api.nonlinear_truss import (
    PublicTwoBarTrussConfig,
    analyze_public_two_bar_truss,
    validate_public_two_bar_truss_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="structural-analysis-nonlinear-truss",
        description=(
            "Run the bounded canonical symmetric two-bar stateful nonlinear "
            "truss Developer Preview path."
        ),
    )
    parser.add_argument("model_path", help="Neutral canonical JSON input.")
    parser.add_argument("--load-steps", type=int, default=10)
    parser.add_argument("--max-iterations", type=int, default=40)
    parser.add_argument("--residual-tolerance", type=float, default=1.0e-10)
    parser.add_argument("--increment-tolerance", type=float, default=1.0e-12)
    parser.add_argument("--out", required=True, help="Analysis-result JSON path.")
    parser.add_argument(
        "--report-out",
        required=True,
        help="Validation-report JSON path.",
    )
    args = parser.parse_args(argv)

    try:
        result_path, report_path = resolve_distinct_output_paths(
            Path(args.out),
            Path(args.report_out),
            protected_paths={"model input": Path(args.model_path)},
        )
        config = PublicTwoBarTrussConfig(
            load_steps=args.load_steps,
            residual_tolerance_kn=args.residual_tolerance,
            increment_tolerance_m=args.increment_tolerance,
            maximum_iterations=args.max_iterations,
        )
    except (OutputPathValidationError, ValueError) as error:
        parser.error(str(error))

    model = load_model(args.model_path)
    result = analyze_public_two_bar_truss(model, config)
    report = validate_public_two_bar_truss_result(result)
    write_json_pair(
        result_path,
        result.to_dict(),
        report_path,
        report.to_dict(),
    )
    return 0 if report.contract_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
