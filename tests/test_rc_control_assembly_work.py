"""Source-bound Newton dispatch work across control arms and constant preload."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark import rc_control_seed_runtime as runtime
from structural_analysis.io.neutral.loader import load_neutral_json


@pytest.mark.parametrize("constant", [False, True])
@pytest.mark.parametrize("retained", [False, True])
def test_all_arms_and_preload_keep_exact_steps_with_opted_in_work(
    tmp_path, constant, retained
):
    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    request = BoundedRCFiberDirectControlRequest(
        7,
        (-1e-6, -2e-6, 1e-6),
        allow_reversals=True,
        maximum_reversals=3,
        constant_nodal_loads=(("N3", 0.0, -0.1, 0.0),) if constant else (),
    )
    request = replace(
        request,
        solver_config=replace(
            request.solver_config,
            newton=replace(request.solver_config.newton, terminal_polishing=True),
        ),
    )
    kwargs = (
        learning._arithmetic_kwargs(learning.RETAINED_LEARNING_ARITHMETIC_PROFILE)
        if retained
        else {}
    )
    reports = []
    for enabled, name in [(False, "baseline"), (True, "recorded")]:
        reports.append(
            runtime.benchmark_rc_control_seed_paths(
                model,
                request,
                source_revision="a" * 40,
                output_directory=tmp_path / name,
                proposal=runtime.secant_seed,
                proposal_identity="sha256:" + "b" * 64,
                record_assembly_work=enabled,
                **kwargs,
            )
        )
    assert all(
        r["reference_repeat_exact"] and r["all_execution_work_reported"]
        for r in reports
    )
    assert reports[0]["comparisons"] == reports[1]["comparisons"]
    baseline, recorded = tmp_path / "baseline", tmp_path / "recorded"
    steps = list(baseline.glob("*/*-step.json"))
    assert len(steps) == (16 if constant else 12)
    for path in steps:
        assert path.read_bytes() == (recorded / path.relative_to(baseline)).read_bytes()
    # Recovery has its own outcome file and is outside the Newton-only counter.
    outcomes = [
        (recorded / path.relative_to(baseline)).with_name(
            path.name.removesuffix("-step.json") + "-outcome.json"
        )
        for path in steps
    ]
    assert len(outcomes) == len(steps)
    for path in outcomes:
        outcome = json.loads(path.read_bytes())
        old = json.loads((baseline / path.relative_to(recorded)).read_bytes())
        assert "newton_assembly_work" not in old
        work = outcome["newton_assembly_work"]
        assert work["call_count"] == work["returned_count"] == len(work["calls"])
        assert work["call_count"] > 0
        assert work["exception_count"] == work["in_flight_count"] == 0
        assert work["calls"][0]["phase"] == "primary_iteration"
        assert work["calls"][-1]["phase"] == "final_observation"
        assert work["outside_newton_assembly_calls"] is None
        assert outcome["work"] == old["work"]
    assert "assembly_work_recording" not in reports[0]
    assert (
        reports[1]["assembly_work_recording"]
        == "vector-newton-assembly-dispatch-work.v1"
    )


@pytest.mark.parametrize("bad", [1, "true", None])
def test_bad_recording_flag_rejects_before_output(tmp_path, bad):
    with pytest.raises(ValueError, match="explicit boolean assembly"):
        runtime.benchmark_rc_control_seed_paths(
            None,
            None,
            source_revision="a" * 40,
            output_directory=tmp_path / "absent",
            record_assembly_work=bad,
        )
    assert not (tmp_path / "absent").exists()


def test_failed_attempt_retains_actual_partial_assembly_work(tmp_path, monkeypatch):
    from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
        StatefulFiberFrame2DDisplacementControlStepAdapter as Adapter,
    )

    original = Adapter.assemble
    calls = 0

    def raise_after_one(self, x):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("observed assembly failure")
        return original(self, x)

    monkeypatch.setattr(Adapter, "assemble", raise_after_one)
    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    report = runtime.benchmark_rc_control_seed_paths(
        model,
        BoundedRCFiberDirectControlRequest(7, (-1e-6,)),
        source_revision="a" * 40,
        output_directory=tmp_path / "failed",
        record_assembly_work=True,
    )
    outcome = json.loads(
        (tmp_path / "failed/reference/000-1-outcome.json").read_bytes()
    )
    assert outcome["status"] == "raised" and outcome["unknown_work"]
    work = outcome["newton_assembly_work"]
    assert work["call_count"] == 2 and work["exception_count"] == 1
    assert not report["all_execution_work_reported"]
    assert not report["comparisons"]["reference"]["full_history_pass"]
