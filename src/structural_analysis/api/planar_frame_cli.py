"""CLI for ``planar_frame_verified_alpha.v1``."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from structural_analysis.api._output_integrity import (
    OutputPathValidationError,
    resolve_distinct_output_bundle_paths,
    resolve_distinct_output_paths,
    write_json_pair,
    write_json_pair_and_bytes,
    write_json_pair_and_clear_artifact,
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
    parser.add_argument("--restart-checkpoint")
    parser.add_argument("--checkpoint-out")
    parser.add_argument("--out", required=True)
    parser.add_argument("--report-out", required=True)
    args = parser.parse_args(argv)

    try:
        protected_paths = {"model input": Path(args.model_path)}
        if args.restart_checkpoint:
            protected_paths["restart checkpoint"] = Path(args.restart_checkpoint)
        if args.checkpoint_out:
            resolved = resolve_distinct_output_bundle_paths(
                {
                    "--out": Path(args.out),
                    "--report-out": Path(args.report_out),
                    "--checkpoint-out": Path(args.checkpoint_out),
                },
                protected_paths=protected_paths,
            )
            out = resolved["--out"]
            report_out = resolved["--report-out"]
            checkpoint_out = resolved["--checkpoint-out"]
        else:
            out, report_out = resolve_distinct_output_paths(
                Path(args.out),
                Path(args.report_out),
                protected_paths=protected_paths,
            )
            checkpoint_out = None

        restart_checkpoint = (
            Path(args.restart_checkpoint).read_bytes()
            if args.restart_checkpoint
            else None
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
            restart_checkpoint_chain=restart_checkpoint,
        )
        report = validate_planar_frame_result(result)
    except (
        OSError,
        OutputPathValidationError,
        PlanarFrameUnsupportedError,
        ValueError,
    ) as error:
        parser.error(str(error))

    result_payload = result.to_dict()
    report_payload = report.to_dict()
    if checkpoint_out is None:
        write_json_pair(out, result_payload, report_out, report_payload)
    else:
        try:
            checkpoint_payload = result.checkpoint_artifact()
        except ValueError:
            write_json_pair_and_clear_artifact(
                out,
                result_payload,
                report_out,
                report_payload,
                checkpoint_out,
            )
        else:
            write_json_pair_and_bytes(
                out,
                result_payload,
                report_out,
                report_payload,
                checkpoint_out,
                checkpoint_payload,
            )
    return 0 if result.status == "converged" else 2


if __name__ == "__main__":
    raise SystemExit(main())
