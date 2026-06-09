"""Tests for checkpointed uncoarsened-boundary P-Delta continuation receipts."""

from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1.build_mgt_uncoarsened_boundary_pdelta_checkpoint_continuation import (
    build_checkpoint_continuation_receipt,
)


def _segment(
    path: Path,
    *,
    resume_from: float,
    max_load: float,
    failed: float | None,
    steps: list[tuple[float, bool, float]],
) -> None:
    saved = [
        {
            "path": str(path.with_name(f"accepted_load_{str(load).replace('.', 'p')}.npz")),
            "schema_version": "mgt-uncoarsened-boundary-pdelta-checkpoint.v1",
            "load_scale": load,
            "dof_count": 12,
            "node_count": 2,
            "residual_inf_n": 1.0e-5,
            "equilibrium_replay_residual_inf_n": 1.0e-5,
            "solver_residual_inf_n": 1.0e-5,
            "equilibrium_replay_gate_passed": True,
            "fixed_point_relative_increment": inc,
            "max_translation_m": 0.1,
        }
        for load, ready, inc in steps
        if ready
    ]
    payload = {
        "schema_version": "mgt-uncoarsened-boundary-pdelta-probe.v1",
        "status": "partial",
        "max_converged_load_scale": max_load,
        "first_failed_load_scale": failed,
        "checkpoint_resume": {
            "resume_from_load_scale": resume_from,
            "resume_checkpoint": {
                "schema_version": "mgt-uncoarsened-boundary-pdelta-checkpoint.v1",
                "load_scale": resume_from,
            },
            "attempted_load_steps_after_resume": [load for load, _ready, _inc in steps],
            "saved_checkpoints": saved,
        },
        "step_results": [
            {
                "load_scale": load,
                "ready": ready,
                "iteration_count": 3,
                "max_iterations": 8,
                "relaxation_factor": 0.5,
                "best_residual_inf_n": 1.0e-5,
                "best_equilibrium_replay_residual_inf_n": 1.0e-5,
                "best_solver_residual_inf_n": 1.0e-5,
                "equilibrium_replay_gate_passed": ready,
                "best_fixed_point_relative_increment": inc,
                "residual_tolerance_n": 5.0e-4,
                "relative_increment_tolerance": 1.0e-4,
                "final_max_translation_m": 0.1,
                "blockers": [] if ready else ["uncoarsened_boundary_pdelta_step_not_converged"],
                **(
                    {
                        "initial_seed_strategy": "seed_alpha_scan_best_candidate",
                        "seed_alpha_scan": {
                            "enabled": True,
                            "best_alpha": 0.25,
                            "best_ready": ready,
                        },
                    }
                    if load == max_load
                    else {}
                ),
            }
            for load, ready, inc in steps
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_checkpoint_continuation_receipt_aggregates_frontier_and_failure(tmp_path: Path) -> None:
    first = tmp_path / "segment-1.json"
    second = tmp_path / "segment-2.json"
    _segment(
        first,
        resume_from=0.45,
        max_load=0.46,
        failed=None,
        steps=[(0.451, True, 6.0e-5), (0.46, True, 7.0e-5)],
    )
    _segment(
        second,
        resume_from=0.46,
        max_load=0.47,
        failed=0.48,
        steps=[(0.47, True, 7.5e-5), (0.48, False, 1.2e-4)],
    )
    out = tmp_path / "aggregate.json"

    payload = build_checkpoint_continuation_receipt(
        segment_paths=[first, second],
        output_json=out,
        source_checkpoint_npz=tmp_path / "accepted_load_0p45.npz",
    )

    assert payload["schema_version"] == "mgt-uncoarsened-boundary-pdelta-checkpoint-continuation.v1"
    assert payload["status"] == "partial"
    assert payload["max_converged_load_scale"] == 0.47
    assert payload["first_failed_load_scale"] == 0.48
    assert payload["accepted_step_count"] == 3
    assert payload["failed_step_count"] == 1
    assert payload["frontier_step"]["load_scale"] == 0.47
    assert payload["frontier_step"]["initial_seed_strategy"] == "seed_alpha_scan_best_candidate"
    assert payload["frontier_step"]["seed_alpha_scan"]["best_alpha"] == 0.25
    assert payload["first_failed_step"]["load_scale"] == 0.48
    assert payload["saved_checkpoint_count"] == 3
    assert json.loads(out.read_text(encoding="utf-8"))["max_converged_load_scale"] == 0.47
