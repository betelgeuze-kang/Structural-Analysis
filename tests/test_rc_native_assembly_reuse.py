"""Native RC opt-in reuse: exact history, real dispatch accounting and boundaries."""

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.assembly import initial_stateful_fiber_frame2d_checkpoint
from structural_analysis.assembly import (
    stateful_fiber_frame2d_displacement_control as control,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark import rc_control_seed_runtime as runtime
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.solvers.nonlinear.assembly_work import (
    VectorAssemblyWorkRecorder,
    VectorLineSearchAssemblyReuse,
    assemble_vector,
)


class Problem:
    def __init__(self):
        self.fail = False

    def assemble(self, coordinates):
        if self.fail:
            raise RuntimeError("original assembly failure")
        return np.array([1.0]), np.array([[2.0]])

    def assemble_with_compensation(self, coordinates, compensation):
        return self.assemble(coordinates)


@pytest.mark.parametrize(
    "boundary",
    [
        "same",
        "coordinate",
        "compensation",
        "final_observation",
        "terminal_refinement",
        "blocked_observation",
    ],
)
def test_native_cache_boundaries_and_real_work(boundary):
    p, work = Problem(), VectorAssemblyWorkRecorder()
    reuse = VectorLineSearchAssemblyReuse(p)
    original = assemble_vector(
        p, np.array([0.0]), phase="line_search", recorder=work, reuse=reuse
    )
    original[0][0] = 99
    result = assemble_vector(
        p,
        np.array([1.0 if boundary == "coordinate" else 0.0]),
        phase=boundary
        if boundary.endswith("observation") or boundary == "terminal_refinement"
        else "primary_iteration",
        compensation=np.array([0.0]) if boundary == "compensation" else None,
        recorder=work,
        reuse=reuse,
    )
    assert result[0][0] == 1
    counts = work.to_dict()
    assert counts["call_count"] == (1 if boundary == "same" else 2)
    assert counts.get("line_search_reuse_hit_count", 0) == (
        1 if boundary == "same" else 0
    )
    assemble_vector(
        p, np.array([0.0]), phase="primary_iteration", recorder=work, reuse=reuse
    )
    assert work.to_dict()["call_count"] == counts["call_count"] + 1


def test_native_failure_clears_pending_and_preserves_spent_call():
    p, work = Problem(), VectorAssemblyWorkRecorder()
    reuse = VectorLineSearchAssemblyReuse(p)
    assemble_vector(p, np.array([0.0]), phase="line_search", recorder=work, reuse=reuse)
    p.fail = True
    with pytest.raises(RuntimeError, match="original assembly failure"):
        assemble_vector(
            p, np.array([1.0]), phase="line_search", recorder=work, reuse=reuse
        )
    p.fail = False
    assemble_vector(
        p, np.array([0.0]), phase="primary_iteration", recorder=work, reuse=reuse
    )
    assert work.to_dict()["call_count"] == 3
    assert work.to_dict()["exception_count"] == 1
    with pytest.raises(ValueError, match="different problem"):
        assemble_vector(
            Problem(), np.array([0.0]), phase="primary_iteration", reuse=reuse
        )


@pytest.mark.parametrize("bad", [None, 1, "true"])
def test_reuse_flag_boundary_before_output(tmp_path, bad):
    with pytest.raises(ValueError, match="boolean line-search assembly reuse"):
        runtime.benchmark_rc_control_seed_paths(
            None,
            None,
            source_revision="a" * 40,
            output_directory=tmp_path / "absent",
            reuse_line_search_assembly=bad,
        )
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("constant", [False, True])
def test_native_full_paths_exact_with_separate_hit_accounting(
    tmp_path, retained, constant
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
    reports, counts, hits = [], [], []
    for enabled in (False, True):
        root = tmp_path / str(enabled)
        report = runtime.benchmark_rc_control_seed_paths(
            model,
            request,
            source_revision="a" * 40,
            output_directory=root,
            proposal=runtime.secant_seed,
            proposal_identity="sha256:" + "b" * 64,
            record_assembly_work=True,
            reuse_line_search_assembly=enabled,
            **(
                learning._arithmetic_kwargs(
                    learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
                )
                if retained
                else {}
            ),
        )
        assert (
            report["reference_repeat_exact"] and report["all_execution_work_reported"]
        )
        assert all(v["full_history_pass"] for v in report["comparisons"].values())
        manifest = json.loads((root / "request.json").read_bytes())
        assert ("line_search_assembly_reuse" in manifest) is enabled
        work = [
            json.loads(
                p.with_name(p.name.replace("-step.json", "-outcome.json")).read_bytes()
            )["newton_assembly_work"]
            for p in root.glob("*/*-step.json")
        ]
        counts.append(sum(w["call_count"] for w in work))
        hits.append(sum(w.get("line_search_reuse_hit_count", 0) for w in work))
        reports.append(report)
    assert reports[0]["comparisons"] == reports[1]["comparisons"]
    assert hits[0] == 0 and hits[1] > 0 and counts[0] == counts[1] + hits[1]
    for p in (tmp_path / "False").glob("*/*-step.json"):
        assert (
            p.read_bytes()
            == (tmp_path / "True" / p.relative_to(tmp_path / "False")).read_bytes()
        )


def test_native_failed_rc_solve_preserves_parent_and_exact_blocked_result():
    model = load_neutral_json(
        Path("examples/public_rc_fiber_frame_l_frame_material_history.json")
    )
    compiled, unsupported, _ = public_api._compile(model)
    assert compiled is not None and not unsupported
    parent = initial_stateful_fiber_frame2d_checkpoint(compiled.problem)
    before = parent.canonical_bytes()
    results = []
    for enabled in (False, True):
        work = VectorAssemblyWorkRecorder()
        result = control.solve_stateful_fiber_frame2d_displacement_control_step(
            compiled.problem,
            parent,
            control_global_dof=7,
            target_control_displacement_m=-1e-6,
            config=control.StatefulFiberFrame2DDisplacementControlConfig(
                newton=NewtonRaphsonConfig(max_iterations=0)
            ),
            assembly_work=work,
            reuse_line_search_assembly=enabled,
        )
        assert result.status == "blocked" and not result.committed
        assert result.accepted_checkpoint is parent
        assert result.metrics["rollback_exact"]
        assert parent.canonical_bytes() == before
        assert work.to_dict()["calls"][-1]["phase"] == "blocked_observation"
        results.append(result.to_dict())
    assert results[0] == results[1]
