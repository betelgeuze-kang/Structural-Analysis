"""Reservation hook ordering without executing a nonlinear solver."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from structural_analysis.api import frame3d_direct_control as api
from structural_analysis.assembly import (
    stateful_corotational_frame3d_displacement_control as core,
)
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.model_ir import load_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("external reservation failed"),
        RuntimeError("external callback failed"),
        JobServiceError("execution_attempt_budget_exhausted", "/budget", "exhausted"),
    ],
)
def test_api_propagates_original_hook_failure_before_numerical_step(
    monkeypatch, failure
):
    document = load_model_ir_v2(
        ROOT / "examples/bounded_frame3d_direct_control.model-ir.v2.json"
    )
    config = api.BoundedFrame3DDirectControlConfig("N2", "UY", (-8.0e-6,))
    callbacks = []

    def reserve():
        callbacks.append(True)
        raise failure

    def forbidden(*args, **kwargs):
        pytest.fail("denied reservation must precede the actual numerical step")

    monkeypatch.setattr(
        core, "solve_stateful_corotational_frame3d_displacement_control_step", forbidden
    )
    with pytest.raises(type(failure)) as raised:
        api.analyze_bounded_frame3d_direct_control_model_ir(
            document,
            config,
            before_solve_attempt=reserve,
        )
    assert raised.value is failure
    assert callbacks == [True]


def test_each_adaptive_retry_reserves_before_increment_or_step(monkeypatch):
    # This fixture has no engineering authority: only retry scheduling/order is
    # exercised. The first fake step rejects; reservation denies its retry.
    parent = SimpleNamespace(
        checkpoint_hash="sha256:" + "1" * 64,
        material_states=(),
        displacement=(0.0,) * 12,
    )
    config = core.StatefulCorotationalFrame3DDisplacementControlConfig()
    attempts = [0]
    history = []
    events = []
    failure = JobServiceError(
        "execution_attempt_budget_exhausted", "/budget", "exhausted"
    )

    def reserve():
        events.append(("reserve", attempts[0]))
        if attempts[0] == 1:
            raise failure

    def reject(*args, **kwargs):
        events.append(("step", attempts[0]))
        return SimpleNamespace(
            committed=False,
            accepted_checkpoint=None,
            solution=SimpleNamespace(
                reason_code="direct_control_maximum_iterations_exceeded",
                metrics={"inadmissible_trial_count": 0},
            ),
            result_hash="sha256:" + "2" * 64,
        )

    monkeypatch.setattr(
        core, "solve_stateful_corotational_frame3d_displacement_control_step", reject
    )
    with pytest.raises(JobServiceError) as raised:
        core._solve_target_with_adaptive_target_cutback(
            object(),
            config,
            control_global_dof=6,
            cumulative_target_index=1,
            leg_direction_sign=1,
            reversal_from_previous_leg=False,
            requested_target=0.004,
            target=0.004,
            parent=parent,
            history=history,
            solve_attempt_counter=attempts,
            before_solve_attempt=reserve,
        )
    assert raised.value is failure
    assert events == [("reserve", 0), ("step", 1), ("reserve", 1)]
    assert attempts == [1]
    assert len(history) == 1
    assert history[0].outcome == "cutback_scheduled"
    assert parent.displacement == (0.0,) * 12
