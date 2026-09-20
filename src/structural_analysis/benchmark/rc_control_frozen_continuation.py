"""Fixed-parent numerical continuation; intermediate states are never adopted."""

from time import perf_counter_ns

from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlStepAdapter,
    solve_stateful_fiber_frame2d_displacement_control_step,
)
from structural_analysis.solvers.nonlinear.assembly_work import VectorAssemblyWorkRecorder

FROZEN_CONTINUATION_FAILURE_IDENTITY = "experimental-frozen-parent-failed-reversal-16.v1"
FROZEN_CONTINUATION_IDENTITY = "experimental-frozen-parent-reversal-16.v1"


class FrozenParentContinuationProposal:
    """Sixteen trial targets with one immutable original material parent."""

    def __call__(self, context):
        raise RuntimeError("native parent and scoped work recording required")

    def propose(self, problem, parent, request, context, *, artifact_sink):
        if problem.coordinate_precision != "binary64":
            raise ValueError("frozen-parent proposal requires binary64 coordinates")
        previous = context.accepted_targets_m
        report = {
            "status": "abstained", "seed": None, "unknown_work": False,
            "native_core_calls_attempted": 0, "known_newton_iterations": 0,
            "known_linear_solves": 0, "stages": [],
            "intermediate_material_checkpoints_adopted": False,
            "parent_hash": parent.state_hash,
        }
        if len(previous) < 2 or (
            (previous[-1] - previous[-2]) * (context.target_m - previous[-1]) >= 0
        ):
            report["reason"] = "no_accepted_direction_reversal"
            return report
        origin = parent.global_displacements[request.control_global_dof]
        if abs(origin - previous[-1]) > request.solver_config.control_tolerance_m:
            raise ValueError("accepted target must match original parent")
        adapter = StatefulFiberFrame2DDisplacementControlStepAdapter(
            problem, parent, request.control_global_dof, context.target_m,
            request.solver_config,
        )
        seed = tuple(adapter.initial_free_displacements_m())
        before = parent.canonical_bytes()
        targets = [origin + (context.target_m - origin) * i / 16 for i in range(1, 17)]
        targets[-1] = context.target_m
        started = perf_counter_ns()
        report.update(status="failed", maximum_native_calls=16, trial_targets_m=targets)
        try:
            for index, target in enumerate(targets):
                recorder = VectorAssemblyWorkRecorder(record_wall_time=True)
                stage = {
                    "index": index, "target_m": target,
                    "parent_hash": parent.state_hash, "unknown_work": True,
                }
                report["stages"].append(stage)
                report["native_core_calls_attempted"] += 1
                tick = perf_counter_ns()
                try:
                    result = solve_stateful_fiber_frame2d_displacement_control_step(
                        problem, parent, control_global_dof=request.control_global_dof,
                        target_control_displacement_m=target, config=request.solver_config,
                        initial_augmented_coordinates_m=seed, assembly_work=recorder,
                    )
                    metrics = result.trial_solution.metrics
                    stage.update(
                        unknown_work=False, committed=result.committed,
                        terminal_reason=metrics["terminal_reason"],
                        relative_residual=metrics["relative_residual"],
                        newton_iterations=metrics["newton_iteration_count"],
                        linear_solves=metrics["linear_solve_count"],
                    )
                    report["known_newton_iterations"] += stage["newton_iterations"]
                    report["known_linear_solves"] += stage["linear_solves"]
                    stage["artifact"] = artifact_sink(index, result.to_dict())
                    if not result.committed:
                        report.update(status="blocked", reason="trial_stage_not_accepted")
                        break
                    # Only coordinates travel to the next trial. Always retain parent.
                    seed = tuple(result.trial_solution.free_displacements_m)
                finally:
                    stage.update(wall_ns=perf_counter_ns() - tick,
                                 assembly_work=recorder.to_dict())
                    if parent.canonical_bytes() != before:
                        raise RuntimeError("continuation mutated original parent")
            else:
                report.update(status="returned", seed=list(seed))
        except Exception as exc:
            report.update(unknown_work=True, error_type=type(exc).__name__, error=str(exc))
        finally:
            report.update(wall_ns=perf_counter_ns() - started,
                          parent_unchanged=parent.canonical_bytes() == before)
            if not report["parent_unchanged"]:
                raise RuntimeError("continuation mutated original parent")
        return report
