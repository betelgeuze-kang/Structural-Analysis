"""Fixed-parent numerical continuation; intermediate states are never adopted."""

from time import perf_counter_ns

from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlStepAdapter,
    solve_stateful_fiber_frame2d_displacement_control_step,
)
from structural_analysis.solvers.nonlinear.assembly_work import VectorAssemblyWorkRecorder

ADAPTIVE_FROZEN_CONTINUATION_IDENTITY = "experimental-frozen-parent-adaptive-failed-target-64.v1"
FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY = "experimental-frozen-parent-failed-target-16.v1"
FROZEN_CONTINUATION_FAILURE_IDENTITY = "experimental-frozen-parent-failed-reversal-16.v1"
FROZEN_CONTINUATION_IDENTITY = "experimental-frozen-parent-reversal-16.v1"


class FrozenParentContinuationProposal:
    """Bounded coordinate trials with one immutable original material parent."""

    def __call__(self, context):
        raise RuntimeError("native parent and scoped work recording required")

    def propose(self, problem, parent, request, context, *, artifact_sink, allow_nonreversal=False, adaptive=False):
        if problem.coordinate_precision not in ("binary64", "twofold-increment"):
            raise ValueError("supported native continuation coordinates required")
        if type(allow_nonreversal) is not bool:
            raise ValueError("explicit boolean target continuation scope required")
        if type(adaptive) is not bool:
            raise ValueError("explicit boolean adaptive continuation required")
        previous = context.accepted_targets_m
        if not previous:
            raise ValueError("accepted origin required for continuation")
        report = {
            "status": "abstained", "seed": None, "unknown_work": False,
            "native_core_calls_attempted": 0, "known_newton_iterations": 0,
            "known_linear_solves": 0, "stages": [],
            "intermediate_material_checkpoints_adopted": False,
            "parent_hash": parent.state_hash,
        }
        if problem.coordinate_precision == "twofold-increment":
            report.update(coordinate_precision="twofold-increment",
                          seed_coordinate_representation="binary64_absolute_high")
        if not allow_nonreversal and (len(previous) < 2 or (
            (previous[-1] - previous[-2]) * (context.target_m - previous[-1]) >= 0
        )):
            report["reason"] = "no_accepted_direction_reversal"
            return report
        origin = parent.global_displacements[request.control_global_dof]
        if abs(origin - previous[-1]) > request.solver_config.control_tolerance_m:
            raise ValueError("accepted target must match original parent")
        adapter = StatefulFiberFrame2DDisplacementControlStepAdapter(
            problem, parent, request.control_global_dof, context.target_m,
            request.solver_config,
        )
        # Native seed inputs are absolute coordinates; retained solver coordinates
        # are increments from the unchanged parent, initially zero.
        absolute, _ = adapter.absolute_coordinates(adapter.initial_free_displacements_m())
        seed = tuple(absolute)
        before = parent.canonical_bytes()
        targets = [origin + (context.target_m - origin) * i / 16 for i in range(1, 17)]
        targets[-1] = context.target_m
        maximum_calls = 64 if adaptive else 16
        fraction, increment = 0., 1 / 16
        started = perf_counter_ns()
        report.update(status="failed", maximum_native_calls=maximum_calls,
                      trial_targets_m=[] if adaptive else targets)
        if adaptive:
            report.update(adaptive=True, minimum_fraction_increment=2**-20,
                          maximum_fraction_increment=1 / 16)
        try:
            for index in range(maximum_calls):
                proposed = min(1., fraction + increment) if adaptive else (index + 1) / 16
                target = (context.target_m if proposed == 1. else
                          origin + (context.target_m - origin) * proposed) if adaptive else targets[index]
                if adaptive:
                    report["trial_targets_m"].append(target)
                recorder = VectorAssemblyWorkRecorder(record_wall_time=True)
                stage = {
                    "index": index, "target_m": target,
                    "parent_hash": parent.state_hash, "unknown_work": True,
                }
                if adaptive:
                    stage.update(last_accepted_fraction=fraction, fraction=proposed,
                                 fraction_increment=increment)
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
                        if adaptive:
                            increment /= 2
                            if increment >= 2**-20:
                                continue
                        report.update(status="blocked", reason=(
                            "minimum_fraction_increment" if adaptive else "trial_stage_not_accepted"
                        ))
                        break
                    # Only coordinates travel to the next trial. Always retain parent.
                    seed = tuple(
                        result.metrics["absolute_augmented_coordinates_m"]
                        if problem.coordinate_precision == "twofold-increment"
                        else result.trial_solution.free_displacements_m
                    )
                    if adaptive:
                        fraction = proposed
                        increment = min(1 / 16, 2 * increment)
                        if fraction == 1.:
                            report.update(status="returned", seed=list(seed))
                            break
                finally:
                    stage.update(wall_ns=perf_counter_ns() - tick,
                                 assembly_work=recorder.to_dict())
                    if parent.canonical_bytes() != before:
                        raise RuntimeError("continuation mutated original parent")
            else:
                if adaptive:
                    report.update(status="blocked", reason="native_trial_budget_exhausted")
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
