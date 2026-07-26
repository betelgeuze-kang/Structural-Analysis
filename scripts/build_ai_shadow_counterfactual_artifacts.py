#!/usr/bin/env python3
"""Build deterministic, non-authoritative PR 18 shadow evaluation artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from structural_analysis.ai.fiber_frame_solver_episode_adapter import (
    create_fiber_frame_solver_episode_adapter,
)
from structural_analysis.ai.offline_counterfactual import (
    DatasetSplit,
    OfflineCounterfactualDataset,
    OfflineCounterfactualSource,
    ShadowPolicyScorecard,
    build_offline_counterfactual_dataset,
    build_shadow_policy_scorecard,
    replay_fiber_frame_counterfactual_transition,
)
from structural_analysis.assembly import (
    make_stateful_fiber_frame2d_checkpoint_chain,
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    create_fiber_frame_nonlinear_kinematic_state_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    create_fiber_frame_material_state_projection_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    create_fiber_frame_nonlinear_execution_state_binding,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
    create_fiber_frame_nonlinear_terminal_receipt,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    create_stateful_fiber_frame2d_physical_equation_scaling,
)
from structural_analysis.benchmark import (
    make_two_element_stateful_fiber_cantilever,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "artifacts/ai/offline_counterfactual_dataset.json"
SCORECARD_PATH = ROOT / "artifacts/ai/shadow_policy_scorecard.json"
# A decreasing-increment path makes the locked residual policy's intervention
# distinct from, and locally comparable with, each deterministic baseline step.
# This is a contract fixture, not a representative performance sample.
LOAD_FACTORS = (0.6, 0.85, 0.95, 0.99, 1.0)


def _source(
    *,
    model_group_id: str,
    split: DatasetSplit,
    angle_rad: float,
    tip_shear_kn: float,
) -> OfflineCounterfactualSource:
    problem = make_two_element_stateful_fiber_cantilever(
        angle_rad=angle_rad,
        tip_shear_kn=tip_shear_kn,
    )
    config = NewtonRaphsonConfig(max_iterations=40)
    path = run_stateful_fiber_frame2d_load_path(
        problem,
        LOAD_FACTORS,
        config=config,
    )
    if path.status != "ready" or not path.contract_pass:
        raise RuntimeError(f"baseline path did not converge for {model_group_id}")

    checkpoints = (
        path.initial_checkpoint,
        *(step.accepted_checkpoint for step in path.steps if step.committed),
    )
    chain = make_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoints)
    model_ir_content_hash = canonical_hash(
        {
            "schema_version": "pr18-offline-model-lineage.v1",
            "model_group_id": model_group_id,
            "problem_contract_hash": problem.contract_hash,
        }
    )
    plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=model_ir_content_hash,
        node_ids=("N1", "N2", "N3"),
    )
    scaling = create_stateful_fiber_frame2d_physical_equation_scaling(problem, plan)
    kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        chain,
    )
    material = create_fiber_frame_material_state_projection_chain(
        problem,
        chain,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hashes=kinematic.solver_state_hashes,
    )
    execution_binding = create_fiber_frame_nonlinear_execution_state_binding(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
    )
    terminal = create_fiber_frame_nonlinear_terminal_receipt(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        execution_binding,
        path,
    )
    adapter = create_fiber_frame_solver_episode_adapter(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        execution_binding,
        path,
        terminal_receipt=terminal,
        episode_mode="shadow",
    )
    outcomes = []
    for transition in adapter.transition_bindings:
        if transition.shadow_disposition != "shadow_only" or transition.shadow_ood:
            continue
        proposed_step_size = transition.shadow_proposed_step_size
        action_hash = transition.shadow_action_payload_hash
        if proposed_step_size is None or action_hash is None:
            raise RuntimeError("eligible shadow transition lacks its action binding")
        if abs(proposed_step_size - transition.baseline_step_size) <= 1.0e-15:
            continue
        outcomes.append(
            replay_fiber_frame_counterfactual_transition(
                problem,
                path,
                adapter,
                transition.transition_index,
                config=config,
            )
        )
    return OfflineCounterfactualSource(
        model_group_id=model_group_id,
        split=split,
        adapter=adapter,
        outcomes=tuple(outcomes),
    )


def build_sources() -> tuple[OfflineCounterfactualSource, ...]:
    return (
        _source(
            model_group_id="cantilever-angle-0-load-10",
            split="calibration",
            angle_rad=0.0,
            tip_shear_kn=-10.0,
        ),
        _source(
            model_group_id="cantilever-angle-0p17-load-12",
            split="validation",
            angle_rad=0.17,
            tip_shear_kn=-12.0,
        ),
        _source(
            model_group_id="cantilever-angle-neg0p23-load-8",
            split="holdout",
            angle_rad=-0.23,
            tip_shear_kn=-8.0,
        ),
    )


def build_artifacts() -> tuple[
    OfflineCounterfactualDataset,
    ShadowPolicyScorecard,
]:
    sources = build_sources()
    dataset = build_offline_counterfactual_dataset(sources)
    scorecard = build_shadow_policy_scorecard(dataset)
    return dataset, scorecard


def _render(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _check(path: Path, expected: bytes) -> bool:
    if not path.is_file():
        print(f"missing generated artifact: {path.relative_to(ROOT)}")
        return False
    if path.read_bytes() != expected:
        print(f"stale generated artifact: {path.relative_to(ROOT)}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when committed artifacts differ from a deterministic rebuild",
    )
    args = parser.parse_args()
    dataset, scorecard = build_artifacts()
    outputs = (
        (DATASET_PATH, _render(dataset.to_dict())),
        (SCORECARD_PATH, _render(scorecard.to_dict())),
    )
    if args.check:
        return 0 if all(_check(path, content) for path, content in outputs) else 1
    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"wrote {path.relative_to(ROOT)}")
    print(f"dataset_hash={dataset.dataset_hash}")
    print(f"scorecard_hash={scorecard.scorecard_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
