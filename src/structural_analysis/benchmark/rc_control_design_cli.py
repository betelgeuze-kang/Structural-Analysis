"""Compare physical RC alternatives on a user-authored experimental control path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.fiber_frame_design_cli import (
    read_design_experiment_with_material_history,
)
from structural_analysis.benchmark.rc_control_design import compare_rc_control_designs
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"input exceeds {limit} bytes: {path}")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "request", "experiment", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args(argv)
    model = load_neutral_json_bytes(
        _read(args.model, 16 * 1024 * 1024), source_path=str(args.model)
    )
    request = decode_bounded_rc_fiber_direct_control_request(
        _read(args.request, 128 * 1024)
    )
    candidates, prices, terminal, history, material = (
        read_design_experiment_with_material_history(args.experiment)
    )
    report = compare_rc_control_designs(
        model,
        candidates,
        request,
        history_limits=history,
        material_limits=material,
        terminal_limits=terminal,
        prices=prices,
        source_revision=args.source_revision,
        output_directory=args.output,
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "report_hash",
                    "candidate_denominator",
                    "verified_count",
                    "selected_candidate_id",
                    "selection_status",
                )
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
