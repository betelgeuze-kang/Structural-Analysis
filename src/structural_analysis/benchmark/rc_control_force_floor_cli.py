"""Run a prospective pin/roller price shortlist and separate full-pool oracle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.fiber_frame_design_cli import (
    read_design_experiment_with_material_history,
)
from structural_analysis.benchmark.rc_control_design_cli import _read
from structural_analysis.benchmark.rc_control_force_floor_search import (
    compare_rc_control_force_floor_price_search,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


FLOOR_INPUT_SCHEMA = "experimental-rc-control-force-response-floor.v1"


def read_force_response_floor(path: Path) -> dict:
    payload = strict_json_object_bytes(
        _read(path, 128 * 1024), maximum_bytes=128 * 1024
    )
    if (
        set(payload)
        != {
            "schema_version",
            "target_index",
            "target_control_displacement_m",
            "minimum_load_factor",
        }
        or payload["schema_version"] != FLOOR_INPUT_SCHEMA
    ):
        raise ValueError("exact prospective force-response floor input required")
    return {key: value for key, value in payload.items() if key != "schema_version"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "request", "experiment", "floor-plan", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--full-analysis-budget", required=True, type=int)
    parser.add_argument("--reuse-line-search-assembly", action="store_true")
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
    if prices is None or history is None or material is None:
        raise ValueError(
            "prospective search requires prices, history and material limits"
        )
    report = compare_rc_control_force_floor_price_search(
        model,
        candidates,
        request,
        force_response_floor=read_force_response_floor(args.floor_plan),
        history_limits=history,
        material_limits=material,
        terminal_limits=terminal,
        prices=prices,
        source_revision=args.source_revision,
        output_directory=args.output,
        full_analysis_budget=args.full_analysis_budget,
        reuse_line_search_assembly=args.reuse_line_search_assembly,
    )
    print(
        json.dumps(
            {
                "report_hash": report["report_hash"],
                "plan_hash": report["plan_hash"],
                "price_order_selected_candidate_id": report["arms"]["price_order"][
                    "selected_candidate_id"
                ],
                "oracle_selected_candidate_id": report["oracle"][
                    "selected_candidate_id"
                ],
                "cost_audit_status": report["candidate_cost_optimality_audit"][
                    "status"
                ],
                "net_ai_savings_proved": False,
            },
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0 if report["candidate_cost_optimality_audit"]["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
