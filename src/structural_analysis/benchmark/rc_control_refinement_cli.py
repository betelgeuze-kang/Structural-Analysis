"""Run one finite RC candidate pool with explicit response refinement criteria.

Local research only. Refinement criteria do not prove continuum accuracy or design
safety. The same request and physical quantity basis are used at every level.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.api.rc_fiber_frame_direct_control_request import decode_bounded_rc_fiber_direct_control_request
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark.fiber_frame_design_cli import read_design_experiment_with_material_history
from structural_analysis.benchmark.rc_control_design_cli import _read
from structural_analysis.benchmark.rc_control_refinement import RCResponseTolerance, _plan, run_refined_candidate_search
from structural_analysis.benchmark.rc_control_reuse import RCControlResultSession
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def read_refinement(path: Path):
    value = strict_json_object_bytes(_read(path, 64 * 1024), maximum_bytes=64 * 1024)
    if (set(value) != {"schema_version", "levels", "responses"}
            or value["schema_version"] != "local-rc-refinement-input.v1"
            or type(value["levels"]) is not list or type(value["responses"]) is not list):
        raise ValueError("exact refinement input fields required")
    tolerances = []
    for row in value["responses"]:
        if type(row) is not dict or set(row) != {"response", "absolute", "relative"}:
            raise ValueError("exact response tolerance fields required")
        tolerances.append(RCResponseTolerance(**row))
    levels = tuple(value["levels"])
    return levels, _plan(levels, tuple(tolerances))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "request", "experiment", "refinement", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--max-new-model-analyses", type=int, default=18)
    parser.add_argument("--scope-id", default="local-research")
    parser.add_argument("--store-root", type=Path)
    parser.add_argument("--tenant-id", default="local-research")
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
            raise ValueError("40-character source revision required")
        if not 0 <= args.max_new_model_analyses <= 102:
            raise ValueError("new-model budget must be in [0, 102]")
        design._identifier(args.scope_id, "scope_id")
        levels, tolerances = read_refinement(args.refinement)
        model = load_neutral_json_bytes(_read(args.model, 16 * 1024 * 1024), source_path=str(args.model))
        request = decode_bounded_rc_fiber_direct_control_request(_read(args.request, 128 * 1024))
        candidates, prices, terminal, history, material = read_design_experiment_with_material_history(args.experiment)
        if prices is None:
            raise ValueError("explicit prices required")
        repository = None
        if args.store_root is not None:
            from structural_analysis.execution.rc_result_repository import open_local_rc_repository
            repository = open_local_rc_repository(args.store_root, tenant_id=args.tenant_id,
                scope_id=args.scope_id, authorization_token=os.environ.get("STRUCTURAL_RC_STORE_TOKEN", ""))
        session = RCControlResultSession(source_revision=args.source_revision,
                                        scope_id=args.scope_id, repository=repository)
        report = run_refined_candidate_search(model, candidates, request, levels=levels,
            tolerances=tolerances, session=session, scope_id=args.scope_id, prices=prices,
            history_limits=history, material_limits=material, terminal_limits=terminal,
            max_new_model_analyses=args.max_new_model_analyses, output_directory=args.output)
        print(json.dumps(report, allow_nan=False, sort_keys=True))
        return 0 if report["status"] == "pool_minimum_confirmed" else 2
    except (ValueError, OSError) as error:
        print(f"RC refinement failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
