"""Opt-in numerical reversal proposals; original Newton retains acceptance."""

from time import perf_counter_ns

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlStepAdapter,
)

TRUST_REGION_REVERSAL_IDENTITY = "experimental-parent-start-trf-reversal.v1"


class TrustRegionReversalProposal:
    """Fixed-budget research strategy, using only this arm's accepted parent."""

    def __call__(self, context):
        raise RuntimeError("native parent and scoped work recording required")

    def propose(self, problem, parent, request, context):
        if problem.coordinate_precision != "binary64":
            raise ValueError("trust-region proposal requires binary64 coordinates")
        targets = context.accepted_targets_m
        if len(targets) < 2 or (
            (targets[-1] - targets[-2]) * (context.target_m - targets[-1]) >= 0
        ):
            return {
                "status": "abstained", "seed": None, "assembly_attempts": 0,
                "unknown_work": False, "reason": "no_accepted_direction_reversal",
            }
        adapter = StatefulFiberFrame2DDisplacementControlStepAdapter(
            problem, parent, request.control_global_dof, context.target_m,
            request.solver_config,
        )
        before = parent.canonical_bytes()
        counts = {"fun": 0, "jac": 0}
        started = perf_counter_ns()
        report = {
            "status": "failed", "seed": None, "unknown_work": True,
            "parent_hash": parent.state_hash, "target_m": context.target_m,
            "maximum_function_evaluations": 100,
            "optimizer_confers_acceptance": False,
            "assembly_scope": "optimizer_full_residual_and_tangent_callbacks",
        }

        def observe(x, kind):
            counts[kind] += 1
            try:
                return adapter.observe(x)
            finally:
                if parent.canonical_bytes() != before:
                    raise RuntimeError("optimizer mutated accepted parent")

        def fun(x):
            return observe(x, "fun").augmented_residual_kn / adapter.reference_force_scale()

        def jac(x):
            return observe(x, "jac").augmented_jacobian_kn_per_m / adapter.reference_force_scale()

        try:
            import scipy
            from scipy.optimize import least_squares

            report["scipy_version"] = scipy.__version__
            result = least_squares(
                fun, adapter.initial_free_displacements_m(), jac=jac,
                method="trf", loss="linear", x_scale="jac", max_nfev=100,
                ftol=1e-12, xtol=1e-12, gtol=1e-12,
            )
            if not np.all(np.isfinite(result.x)) or not np.all(np.isfinite(result.fun)):
                raise ValueError("nonfinite optimizer candidate")
            report.update(
                status="returned", unknown_work=False, seed=result.x.tolist(),
                optimizer_success=bool(result.success), optimizer_status=int(result.status),
                optimizer_message=str(result.message), nfev=int(result.nfev),
                njev=int(result.njev), residual_inf=float(np.linalg.norm(result.fun, np.inf)),
            )
        except Exception as exc:
            report.update(error_type=type(exc).__name__, error=str(exc))
        finally:
            report.update(
                assembly_attempts=sum(counts.values()), assembly_counts=counts,
                wall_ns=perf_counter_ns() - started,
                parent_unchanged=parent.canonical_bytes() == before,
            )
            if not report["parent_unchanged"]:
                raise RuntimeError("optimizer mutated accepted parent")
        return report
