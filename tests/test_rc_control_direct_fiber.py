"""Direct coordinate-to-fiber trials preserve native solve/recovery authority."""

from dataclasses import replace
from decimal import Decimal, localcontext
import importlib.util
import json
from pathlib import Path
import os
import subprocess
import sys

import numpy as np
import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint as initial,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    dump_stateful_fiber_frame2d_checkpoint_bytes as dump,
    load_stateful_fiber_frame2d_checkpoint_bytes as load,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    solve_stateful_fiber_frame2d_displacement_control_step as solve,
    StatefulFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_material_arithmetic,
    _with_coordinate_precision,
    _with_strain_evaluation,
    _with_fiber_strain_evaluation,
    benchmark_rc_control_seed_paths,
)
from structural_analysis.materials.direct_fiber_strain import (
    coordinate_fiber_strains,
    DIRECT_FIBER_PROFILE,
)
from structural_analysis.materials.trial_runtime import MaterialTrialRuntimeRecorder
from structural_analysis.io.neutral.loader import load_neutral_json

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"


def compiled():
    c, b, _ = _compile(load_neutral_json(MODEL))
    assert not b
    return _with_fiber_strain_evaluation(
        _with_material_arithmetic(
            _with_coordinate_precision(
                _with_strain_evaluation(c, "exact-rational"), "twofold-increment"
            ),
            "stable-stress",
        ),
        "direct-coordinate",
    )


def test_direct_strain_retains_bits_lost_by_rounding_generalized_strains():
    g, fibers = coordinate_fiber_strains(
        [0.0, 0.0, -1.0, 1.0, 0.0, 0.0],
        1.0,
        0.0,
        [1.0],
        [0.0, 0.0, 0.0, 2**-54, 0.0, 0.0],
    )
    assert g[0] - g[1] == 0 and fibers[0] == 2**-54
    assert not fibers.flags.writeable


@pytest.mark.parametrize("length", [1.0, 2.7, 6.3])
def test_direct_strains_match_independent_decimal_polynomial(length):
    high = [0.001, -0.023, 0.0001, 0.006, -0.019, 0.0003]
    low = [1e-20, -3e-19, 7e-22, 0.0, -9e-20, 1e-22]
    locations = [-0.15, 0.0, 0.15]
    xi = 0.7745966692414834
    _, actual = coordinate_fiber_strains(high, length, xi, locations, low)
    with localcontext() as ctx:
        ctx.prec = 100
        D = Decimal.from_float
        L = D(length)
        ratio = (D(xi) + 1) / 2
        u = [D(a) + D(b) for a, b in zip(high, low, strict=True)]
        curvature = (
            (-6 + 12 * ratio) * u[1] / L**2
            + (-4 + 6 * ratio) * u[2] / L
            + (6 - 12 * ratio) * u[4] / L**2
            + (-2 + 6 * ratio) * u[5] / L
        )
        expected = [float((u[3] - u[0]) / L - D(y) * curvature) for y in locations]
    assert np.array_equal(actual, expected)


@pytest.mark.parametrize("scale", [0.05, 1.0, 4.0])
def test_element_tangent_matches_same_parent_finite_difference(scale):
    element = compiled().problem.members[0].element
    parent = element.initial_state()
    raw = parent.to_dict()
    u = np.array([0.0, 0.0, 0.0, 1e-4, -0.001, 0.0002]) * scale
    low = np.zeros(6)
    response = element.integrate(u, parent, local_displacement_compensation=low)
    h = 1e-8
    columns = []
    for j in range(6):
        d = np.zeros(6)
        d[j] = h
        a = element.integrate(u + d, parent, local_displacement_compensation=low)
        b = element.integrate(u - d, parent, local_displacement_compensation=low)
        columns.append((a.internal_force_local - b.internal_force_local) / (2 * h))
    actual = np.array(columns).T
    assert (
        np.linalg.norm(actual - response.consistent_tangent_local, np.inf)
        / np.linalg.norm(actual, np.inf)
        < 2e-5
    )
    assert parent.to_dict() == raw


def test_runtime_covers_every_actual_direct_material_trial_and_original_bytes():
    element = compiled().problem.members[0].element
    parent = element.initial_state()
    u = np.array([0.0, 0.0, 0.0, 1e-4, -0.001, 0.0002])
    low = np.zeros(6)
    plain = element.integrate(u, parent, local_displacement_compensation=low)
    recorder = MaterialTrialRuntimeRecorder()
    timed = element.integrate(
        u, parent, local_displacement_compensation=low, material_runtime=recorder
    )
    assert timed.to_dict() == plain.to_dict()
    assert (
        recorder.coverage_complete
        and recorder.call_count
        == element.integration_order * len(element.section.fibers)
    )
    assert recorder.instrumented_section_call_count == element.integration_order
    with pytest.raises(ValueError, match="requires original element coordinates"):
        element.section.integrate([0.0, 0.0], element.section.initial_state())
    with pytest.raises(ValueError, match="requires exact-rational"):
        replace(element, strain_evaluation="matrix", coordinate_precision="binary64")


def test_native_restart_fresh_interpreter_and_mixed_profile_rejection(tmp_path):
    c = compiled()
    problem = c.problem
    parent = initial(problem)
    for target in [-1e-5, -2e-5]:
        step = solve(
            problem, parent, control_global_dof=7, target_control_displacement_m=target
        )
        assert step.committed
        parent = step.accepted_checkpoint
    raw = dump(problem, parent)
    assert dump(problem, load(raw, problem)) == raw
    (tmp_path / "checkpoint.json").write_bytes(raw)
    expected = solve(
        problem, parent, control_global_dof=7, target_control_displacement_m=-1e-5
    )
    assert expected.committed
    script = """
import importlib.util,json,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('direct_test',Path(sys.argv[1])/'tests/test_rc_control_direct_fiber.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=m.compiled().problem;r=Path(sys.argv[2]);parent=m.load((r/'checkpoint.json').read_bytes(),p)
s=m.solve(p,parent,control_global_dof=7,target_control_displacement_m=-1e-5);assert s.committed
(r/'step.json').write_text(json.dumps(s.to_dict()))
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(ROOT), str(tmp_path)],
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "step.json").read_text()) == expected.to_dict()
    original, b, _ = _compile(load_neutral_json(MODEL))
    assert not b
    for p in [
        original.problem,
        _with_material_arithmetic(
            _with_coordinate_precision(
                _with_strain_evaluation(original, "exact-rational"), "twofold-increment"
            ),
            "stable-stress",
        ).problem,
    ]:
        with pytest.raises(ValueError):
            load(raw, p)


def test_nonconvergence_preserves_original_native_parent():
    problem = compiled().problem
    parent = initial(problem)
    raw = parent.canonical_bytes()
    step = solve(
        problem,
        parent,
        control_global_dof=7,
        target_control_displacement_m=-0.01,
        config=StatefulFiberFrame2DDisplacementControlConfig(
            newton=NewtonRaphsonConfig(max_iterations=1)
        ),
    )
    assert (
        not step.committed
        and step.accepted_checkpoint is parent
        and step.metrics["rollback_exact"]
    )
    assert parent.canonical_bytes() == raw


def test_full_cyclic_recovery_and_saved_force_diagnostic(tmp_path):
    study = tmp_path / "study"
    report = benchmark_rc_control_seed_paths(
        load_neutral_json(MODEL),
        BoundedRCFiberDirectControlRequest(
            7, (-1e-5, -2e-5, -1e-5), allow_reversals=True, maximum_reversals=1
        ),
        source_revision="0" * 40,
        output_directory=study,
        strain_evaluation="exact-rational",
        coordinate_precision="twofold-increment",
        material_arithmetic="stable-stress",
        fiber_strain_evaluation="direct-coordinate",
    )
    assert report["reference_repeat_exact"] and report["all_execution_work_reported"]
    assert report["fiber_strain_evaluation"] == "direct-coordinate"
    for arm in ["reference", "secant", "fresh-reference"]:
        path = json.loads((study / arm / "path.json").read_text())
        assert path["status"] == "complete" and path["accepted_target_count"] == 3
        for p in (study / arm).glob("*-step.json"):
            step = json.loads(p.read_text())
            for member in step["trial_assembly"]["member_assemblies"]:
                assert all(
                    s["fiber_strain_evaluation"] == DIRECT_FIBER_PROFILE
                    for s in member["element_response"]["section_responses"]
                )
    spec = importlib.util.spec_from_file_location(
        "force", ROOT / "scripts/diagnose_rc_control_force_error.py"
    )
    diag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diag)
    assert diag.diagnose(study)["target_count"] == 3


@pytest.mark.parametrize("kwargs", [{}, {"material_arithmetic": "stable-stress"}])
def test_incompatible_profiles_rejected_before_output_creation(tmp_path, kwargs):
    output = tmp_path / "unexpected"
    with pytest.raises(ValueError, match="requires stable-stress and exact-rational"):
        benchmark_rc_control_seed_paths(
            load_neutral_json(MODEL),
            BoundedRCFiberDirectControlRequest(7, (-1e-5,)),
            source_revision="0" * 40,
            output_directory=output,
            fiber_strain_evaluation="direct-coordinate",
            **kwargs,
        )
    assert not output.exists()


def test_custom_direct_coordinate_override_without_timing_is_marked_incomplete():
    from structural_analysis.materials.direct_fiber_strain import DirectFiberRCSection

    class Unmeasured(DirectFiberRCSection):
        def integrate_from_element_coordinates(self, *args, **kwargs):
            kwargs["material_runtime"] = None
            return super().integrate_from_element_coordinates(*args, **kwargs)

    element = compiled().problem.members[0].element
    section = element.section
    element = replace(
        element,
        section=Unmeasured(
            fibers=section.fibers,
            steel=section.steel,
            concrete=section.concrete,
            section_id=section.section_id,
        ),
    )
    recorder = MaterialTrialRuntimeRecorder()
    element.integrate(
        np.zeros(6),
        element.initial_state(),
        local_displacement_compensation=np.zeros(6),
        material_runtime=recorder,
    )
    assert recorder.unmeasured_section_call_count == element.integration_order
    assert not recorder.coverage_complete and recorder.call_count == 0
