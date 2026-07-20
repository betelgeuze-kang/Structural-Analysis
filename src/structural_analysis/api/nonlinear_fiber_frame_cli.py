"""CLI for the bounded public stateful RC fiber-frame path."""

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
from structural_analysis.api.nonlinear_fiber_frame import (
    PublicRCFiberFrameConfig,
    analyze_public_rc_fiber_frame,
    validate_public_rc_fiber_frame_result,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_BYTES,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="structural-analysis-nonlinear-fiber-frame",
        description=(
            "Run the bounded planar serial-cantilever RC fiber-frame "
            "Developer Preview path."
        ),
    )
    parser.add_argument("model_path", help="Neutral canonical JSON input.")
    parser.add_argument("--load-steps", type=int, default=4)
    parser.add_argument("--max-iterations", type=int, default=40)
    parser.add_argument("--residual-tolerance", type=float, default=1.0e-10)
    parser.add_argument("--increment-tolerance", type=float, default=1.0e-12)
    parser.add_argument(
        "--restart-from",
        help="Exact checkpoint-chain artifact from the same model and load prefix.",
    )
    parser.add_argument("--out", required=True, help="Analysis-result JSON path.")
    parser.add_argument(
        "--report-out",
        required=True,
        help="Validation-report JSON path.",
    )
    parser.add_argument(
        "--checkpoint-out",
        help="Optional exact terminal accepted checkpoint-chain output path.",
    )
    args = parser.parse_args(argv)

    protected = {"model input": Path(args.model_path)}
    if args.restart_from is not None:
        protected["restart input"] = Path(args.restart_from)
    try:
        config = PublicRCFiberFrameConfig(
            load_steps=args.load_steps,
            residual_tolerance=args.residual_tolerance,
            increment_tolerance_m=args.increment_tolerance,
            maximum_iterations=args.max_iterations,
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
        restart_bytes = (
            _read_restart_artifact(Path(args.restart_from))
            if args.restart_from is not None
            else None
        )
    except (OSError, OutputPathValidationError, ValueError) as error:
        parser.error(str(error))

    model = load_model(args.model_path)
    result = analyze_public_rc_fiber_frame(
        model,
        config,
        restart_checkpoint_chain=restart_bytes,
    )
    report = validate_public_rc_fiber_frame_result(result)
    if checkpoint_path is not None and result.checkpoint.get("available") is True:
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


def _read_restart_artifact(path: Path) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_BYTES + 1)
    if len(payload) > STATEFUL_FIBER_FRAME2D_CHECKPOINT_CHAIN_MAX_BYTES:
        raise ValueError("restart checkpoint artifact exceeds the bounded byte limit")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
