"""Local persistent cost search; credentials come from the host environment.

The SQLite databases must be on a trusted local filesystem. A new output folder
is required for each invocation. Cancel/pause is at an original chunk boundary;
there is no claim of interruption inside Newton or distributed scheduling.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.api.rc_fiber_frame_direct_control_request import decode_bounded_rc_fiber_direct_control_request
from structural_analysis.benchmark.fiber_frame_design_cli import read_design_experiment_with_material_history
from structural_analysis.benchmark.rc_control_cost_search import run_rc_control_cost_search
from structural_analysis.benchmark.rc_control_durable import DurableRCControlResultSession
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.benchmark.rc_control_design_cli import _read
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("model", "request", "output", "store"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--experiment", type=Path, action="append", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--scope-id", default="local-research")
    parser.add_argument("--max-new-model-analyses", type=int, default=17)
    parser.add_argument("--chunk-target-count", type=int, default=255)
    parser.add_argument("--max-chunks-per-call", type=int, default=255)
    args = parser.parse_args(argv)
    try:
        if not 1 <= len(args.experiment) <= 16 or not 0 <= args.max_new_model_analyses <= 17:
            raise ValueError("scenario or new-model budget out of range")
        tenant_token = os.environ.get("STRUCTURAL_RC_TENANT_TOKEN", "")
        worker_token = os.environ.get("STRUCTURAL_RC_WORKER_TOKEN", "")
        session = DurableRCControlResultSession(
            store_root=args.store, source_revision=args.source_revision, scope_id=args.scope_id,
            authorization_token=tenant_token, worker_token=worker_token,
            chunk_target_count=args.chunk_target_count, max_chunks_per_call=args.max_chunks_per_call)
        raw = _read(args.model, 16 * 1024 * 1024)
        strict_json_object_bytes(raw, maximum_bytes=16 * 1024 * 1024)
        model = load_neutral_json_bytes(raw, source_path=str(args.model))
        request = decode_bounded_rc_fiber_direct_control_request(_read(args.request, 128 * 1024))
        scenarios = [read_design_experiment_with_material_history(path) for path in args.experiment]
        if any(prices is None for _, prices, _, _, _ in scenarios):
            raise ValueError("explicit common prices required")
        args.output.mkdir(parents=True, exist_ok=False)
        budget = args.max_new_model_analyses
        results = []
        for index, (candidates, prices, terminal, history, material) in enumerate(scenarios):
            report = run_rc_control_cost_search(
                model, candidates, request, session=session, scope_id=args.scope_id,
                prices=prices, terminal_limits=terminal, history_limits=history, material_limits=material,
                output_directory=args.output/f"scenario-{index:03d}", max_new_model_analyses=budget)
            budget -= report["new_model_evaluations"]
            results.append({k: report[k] for k in ("status", "report_hash", "cost_bound",
                                                   "new_model_evaluations", "reused_model_evaluations", "new_work")})
            if report["new_work"]["unknown_work"]:
                break
        report = {"schema_version": "local-durable-rc-search-batch.v1", "scenarios": results,
                  "requested_scenario_count": len(scenarios), "remaining_new_model_budget": budget,
                  "claims": {"same_host_persistence": True, "gpu_execution": False,
                             "performance_improvement": False, "design_authority": False}}
        report["report_hash"] = _sha(_bytes(report))
        _save(args.output, "batch.json", _bytes(report))
        print(json.dumps(report, allow_nan=False, sort_keys=True))
        return 0 if len(results) == len(scenarios) and all(r["status"] == "pool_minimum_confirmed" for r in results) else 2
    except (ValueError, OSError):
        # Detailed solver failures live in the authenticated durable records.
        # Do not reflect exception strings or credentials to terminal logs.
        print("durable_rc_search_failed: inspect authenticated job records", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
