"""CLI for the unified bounded nonlinear frame API."""

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
from structural_analysis.api.core import load_model
from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_GENERAL_PROFILE,
    COROTATIONAL_PORTAL_PROFILE,
    FIXED_CHORD_SERIAL_PROFILE,
    NONLINEAR_FRAME_CHECKPOINT_MAX_BYTES,
    NonlinearFrameConfig,
    analyze_nonlinear_frame,
    validate_nonlinear_frame_result,
)
from structural_analysis.solvers.nonlinear.newton import VECTOR_MATRIX_BACKENDS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="structural-analysis-nonlinear-frame",
        description="Run one explicit bounded nonlinear frame profile.",
    )
    parser.add_argument("model_path", help="Neutral canonical JSON input.")
    parser.add_argument(
        "--profile",
        choices=(
            FIXED_CHORD_SERIAL_PROFILE,
            COROTATIONAL_PORTAL_PROFILE,
            COROTATIONAL_GENERAL_PROFILE,
        ),
        default=FIXED_CHORD_SERIAL_PROFILE,
    )
    parser.add_argument("--load-steps", type=int, default=4)
    parser.add_argument(
        "--control-mode",
        choices=("load_control", "direct_displacement_control", "arc_length"),
        default="load_control",
    )
    parser.add_argument("--control-node-id")
    parser.add_argument("--control-dof", choices=("UX", "UY"))
    parser.add_argument(
        "--target-control-displacement",
        type=float,
        action="append",
        default=[],
        help="Control displacement target in metres; repeat for a direct path.",
    )
    parser.add_argument("--max-iterations", type=int, default=40)
    parser.add_argument("--residual-tolerance", type=float, default=1.0e-10)
    parser.add_argument("--increment-tolerance", type=float, default=1.0e-12)
    parser.add_argument("--control-tolerance", type=float, default=1.0e-12)
    parser.add_argument(
        "--load-factor-increment-tolerance",
        type=float,
        default=1.0e-12,
    )
    parser.add_argument(
        "--load-factor-coordinate-scale",
        type=float,
        default=1.0e-3,
    )
    parser.add_argument("--arc-length-initial", type=float, default=6.0e-3)
    parser.add_argument("--arc-length-minimum", type=float, default=7.5e-4)
    parser.add_argument("--arc-length-maximum", type=float, default=6.0e-3)
    parser.add_argument(
        "--arc-length-failed-step-reduction",
        type=float,
        default=0.5,
    )
    parser.add_argument(
        "--arc-length-constraint-tolerance",
        type=float,
        default=1.0e-12,
    )
    parser.add_argument(
        "--arc-length-max-attempts",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--matrix-backend",
        choices=VECTOR_MATRIX_BACKENDS,
        default=VECTOR_MATRIX_BACKENDS[0],
        help="Linear algebra backend (native sparse is corotational-only).",
    )
    parser.add_argument(
        "--restart-from",
        help="Exact checkpoint-chain artifact for the selected model/profile.",
    )
    parser.add_argument("--out", required=True, help="Unified result JSON path.")
    parser.add_argument(
        "--report-out",
        required=True,
        help="Validation report JSON path.",
    )
    parser.add_argument(
        "--checkpoint-out",
        help="Optional terminal checkpoint-chain output path.",
    )
    args = parser.parse_args(argv)

    protected = {"model input": Path(args.model_path)}
    if args.restart_from is not None:
        protected["restart input"] = Path(args.restart_from)
    try:
        config = NonlinearFrameConfig(
            profile=args.profile,
            control_mode=args.control_mode,
            load_steps=args.load_steps,
            residual_tolerance=args.residual_tolerance,
            increment_tolerance_m=args.increment_tolerance,
            maximum_iterations=args.max_iterations,
            matrix_backend=args.matrix_backend,
            control_node_id=args.control_node_id,
            control_dof=args.control_dof,
            target_control_displacements_m=tuple(args.target_control_displacement),
            control_tolerance_m=args.control_tolerance,
            load_factor_increment_tolerance=(args.load_factor_increment_tolerance),
            load_factor_coordinate_scale_m=args.load_factor_coordinate_scale,
            arc_length_initial_m=args.arc_length_initial,
            arc_length_minimum_m=args.arc_length_minimum,
            arc_length_maximum_m=args.arc_length_maximum,
            arc_length_failed_step_reduction=(args.arc_length_failed_step_reduction),
            arc_length_constraint_tolerance_m2=(args.arc_length_constraint_tolerance),
            arc_length_maximum_attempt_count=args.arc_length_max_attempts,
        )
        if args.checkpoint_out is None:
            result_path, report_path = resolve_distinct_output_paths(
                Path(args.out),
                Path(args.report_out),
                protected_paths=protected,
            )
            checkpoint_path = None
        else:
            resolved = resolve_distinct_output_bundle_paths(
                {
                    "--out": Path(args.out),
                    "--report-out": Path(args.report_out),
                    "--checkpoint-out": Path(args.checkpoint_out),
                },
                protected_paths=protected,
            )
            result_path = resolved["--out"]
            report_path = resolved["--report-out"]
            checkpoint_path = resolved["--checkpoint-out"]
        restart = (
            _read_checkpoint_chain(Path(args.restart_from))
            if args.restart_from is not None
            else None
        )
    except (OSError, OutputPathValidationError, ValueError) as error:
        parser.error(str(error))

    result = analyze_nonlinear_frame(
        load_model(args.model_path),
        config,
        restart_checkpoint_chain=restart,
    )
    report = validate_nonlinear_frame_result(result)
    if checkpoint_path is not None and report.checkpoint_available:
        write_json_pair_and_bytes(
            result_path,
            result.to_dict(),
            report_path,
            report.to_dict(),
            checkpoint_path,
            result.checkpoint_artifact(),
        )
    elif checkpoint_path is None:
        write_json_pair(
            result_path,
            result.to_dict(),
            report_path,
            report.to_dict(),
        )
    else:
        write_json_pair_and_clear_artifact(
            result_path,
            result.to_dict(),
            report_path,
            report.to_dict(),
            checkpoint_path,
        )
    return 0 if report.contract_pass else 2


def _read_checkpoint_chain(path: Path) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(NONLINEAR_FRAME_CHECKPOINT_MAX_BYTES + 1)
    if len(payload) > NONLINEAR_FRAME_CHECKPOINT_MAX_BYTES:
        raise ValueError("restart checkpoint artifact exceeds the bounded byte limit")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
