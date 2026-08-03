"""CLI for ``planar_frame_verified_alpha.v1``."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from structural_analysis.api._output_integrity import (
    OutputPathValidationError,
    resolve_distinct_output_paths,
    write_json_pair,
)
from structural_analysis.api.planar_frame import (
    PlanarFrameConfig,
    PlanarFrameUnsupportedError,
    analyze_planar_frame,
    validate_planar_frame_result,
)
from structural_analysis.model_ir import load_model_ir_v2
from structural_analysis.solvers.nonlinear.newton import VECTOR_MATRIX_BACKENDS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="structural-analysis-planar-frame")
    parser.add_argument(
        "model_path", help="planar_frame_verified_alpha.v1 ModelIR v2 JSON"
    )
    parser.add_argument(
        "--control",
        choices=("load_control", "direct_displacement_control", "arc_length"),
        default="load_control",
    )
    parser.add_argument("--load-steps", type=int, default=4)
    parser.add_argument("--max-iterations", type=int, default=40)
    parser.add_argument("--residual-tolerance", type=float, default=1.0e-10)
    parser.add_argument("--increment-tolerance", type=float, default=1.0e-12)
    parser.add_argument(
        "--matrix-backend",
        choices=VECTOR_MATRIX_BACKENDS,
        default=VECTOR_MATRIX_BACKENDS[0],
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--report-out", required=True)
    args = parser.parse_args(argv)

    try:
        out, report_out = resolve_distinct_output_paths(
            Path(args.out),
            Path(args.report_out),
            protected_paths={"model input": Path(args.model_path)},
        )
        result = analyze_planar_frame(
            load_model_ir_v2(args.model_path),
            PlanarFrameConfig(
                control=args.control,
                load_steps=args.load_steps,
                residual_tolerance=args.residual_tolerance,
                increment_tolerance_m=args.increment_tolerance,
                maximum_iterations=args.max_iterations,
                matrix_backend=args.matrix_backend,
            ),
        )
        report = validate_planar_frame_result(result)
    except (
        OSError,
        OutputPathValidationError,
        PlanarFrameUnsupportedError,
        ValueError,
    ) as error:
        parser.error(str(error))
    write_json_pair(out, result.to_dict(), report_out, report.to_dict())
    return 0 if result.status == "converged" else 2


if __name__ == "__main__":
    raise SystemExit(main())
