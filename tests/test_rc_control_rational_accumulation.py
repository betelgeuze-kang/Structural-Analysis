"""Rational accumulation is part of original solve, assembly and native recovery."""

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as F
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
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_material_arithmetic,
    _with_fiber_strain_evaluation,
    _with_coordinate_precision,
    _with_strain_evaluation,
    _with_force_accumulation,
    benchmark_rc_control_seed_paths,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint as initial,
    assemble_stateful_fiber_frame2d as assemble,
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
from structural_analysis.solvers.nonlinear.rational_accumulation import (
    section_values,
)
from structural_analysis.materials.trial_runtime import MaterialTrialRuntimeRecorder
from structural_analysis.io.neutral.loader import load_neutral_json

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"
spec = importlib.util.spec_from_file_location(
    "verify_rational", ROOT / "scripts/verify_rc_rational_assembly.py"
)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def compiled(rational=True):
    c, b, _ = _compile(load_neutral_json(MODEL))
    assert not b
    c = _with_fiber_strain_evaluation(
        _with_material_arithmetic(
            _with_coordinate_precision(
                _with_strain_evaluation(c, "exact-rational"), "twofold-increment"
            ),
            "retained-strain",
        ),
        "retained-coordinate",
    )
    return _with_force_accumulation(c, "rational") if rational else c


def test_exact_section_sum_preserves_opposing_terms():
    from types import SimpleNamespace as O

    fibers = [O(area_m2=0.001, y_m=0.0)] * 3
    responses = [
        O(stress_mpa=v, consistent_tangent_mpa=1.0) for v in [2**53, 1.0, -(2**53)]
    ]
    n, k = section_values(fibers, responses)
    assert n[0] == F(0.001) * 1000 and n[1] == 0
    assert k[0][0] == 3 * F(0.001) * 1000


@pytest.fixture
def record():
    c = compiled()
    p = initial(c.problem)
    s = solve(c.problem, p, control_global_dof=7, target_control_displacement_m=-0.001)
    assert s.committed
    return c, s


def test_dense_independent_record_rebuild_without_material_calls(record, monkeypatch):
    from structural_analysis.materials.retained_fiber_strain import (
        RetainedStrainSteel,
        RetainedStrainConcrete,
    )

    def forbidden(*a, **k):
        pytest.fail("record verifier must not integrate materials")

    monkeypatch.setattr(RetainedStrainSteel, "integrate", forbidden)
    monkeypatch.setattr(RetainedStrainConcrete, "integrate", forbidden)
    c, s = record
    r = verify.verify_assembly(c.problem, s.trial_assembly.to_dict())
    assert r == {
        "section_replays": 6,
        "member_replays": 2,
        "material_integrations": 0,
        "newton_solves": 0,
        "state_commits": 0,
    }


@pytest.mark.parametrize("factor", [0.0, -0.4, 0.7])
def test_original_rational_record_rebuild_keeps_constants_under_reversal(
    factor, monkeypatch
):
    from structural_analysis.api.rc_fiber_frame_direct_control import (
        _with_constant_loading,
    )

    c = _with_constant_loading(compiled(), (("N3", -60.0, -0.1, 0.0),))
    parent = initial(c.problem)
    n = len(c.problem.free_global_dofs)
    record = assemble(
        c.problem,
        parent,
        target_load_factor=factor,
        trial_free_coordinates_m=np.arange(1, n + 1) * -1e-5,
        trial_free_coordinate_compensation_m=np.zeros(n),
    ).to_dict()

    def forbidden(*args, **kwargs):
        pytest.fail("record audit may not assemble or integrate material laws")

    from structural_analysis.materials.retained_fiber_strain import (
        RetainedStrainSteel,
        RetainedStrainConcrete,
    )

    monkeypatch.setattr(RetainedStrainSteel, "integrate", forbidden)
    monkeypatch.setattr(RetainedStrainConcrete, "integrate", forbidden)
    result = verify.verify_assembly(c.problem, record)
    assert result["newton_solves"] == result["material_integrations"] == 0
    changed = deepcopy(record)
    # This is the former proportional-only audit's incorrect external vector.
    changed["external_loads_global"] = [
        factor * float(v) for v in c.problem.reference_external_load_vector()
    ]
    with pytest.raises(ValueError, match="external"):
        verify.verify_assembly(c.problem, changed)


@pytest.mark.parametrize(
    "field",
    ["exact_force", "exact_tangent", "section", "global", "residual", "reaction"],
)
def test_altered_rational_or_display_fields_are_rejected(record, field):
    c, s = record
    a = deepcopy(s.trial_assembly.to_dict())
    r = a["member_assemblies"][0]["element_response"]
    if field == "exact_force":
        r["rational_force_local"][0][0] = str(int(r["rational_force_local"][0][0]) + 1)
    elif field == "exact_tangent":
        r["rational_tangent_local"][0][0][0] = str(
            int(r["rational_tangent_local"][0][0][0]) + 1
        )
    elif field == "section":
        r["section_responses"][0]["consistent_tangent"][0][0] += 1
    elif field == "global":
        a["member_assemblies"][0]["internal_load_global"][0] += 1
    elif field == "residual":
        a["residual_kn"][0] += 1
    else:
        a["reactions_global"][0] += 1
    with pytest.raises(ValueError, match="rational assembly"):
        verify.verify_assembly(c.problem, a)


def test_original_scaled_frame_tangent_and_runtime_coverage():
    c = compiled()
    p = initial(c.problem)
    n = len(c.problem.free_global_dofs)
    u = np.arange(1, n + 1) * -1e-5
    zero = np.zeros(n)
    runtime = MaterialTrialRuntimeRecorder()
    a = assemble(
        c.problem,
        p,
        target_load_factor=0.1,
        trial_free_coordinates_m=u,
        trial_free_coordinate_compensation_m=zero,
        material_runtime=runtime,
    )
    assert runtime.coverage_complete and runtime.call_count == 84
    columns = []
    h = 1e-8
    for i in range(n):
        d = np.zeros(n)
        d[i] = h
        x = assemble(
            c.problem,
            p,
            target_load_factor=0.1,
            trial_free_coordinates_m=u + d,
            trial_free_coordinate_compensation_m=zero,
        )
        y = assemble(
            c.problem,
            p,
            target_load_factor=0.1,
            trial_free_coordinates_m=u - d,
            trial_free_coordinate_compensation_m=zero,
        )
        columns.append((x.residual_kn - y.residual_kn) / (2 * h))
    K = np.array(columns).T
    assert (
        np.linalg.norm(K - a.jacobian_kn_per_m, np.inf) / np.linalg.norm(K, np.inf)
        < 2e-5
    )


def test_native_restart_and_genuine_rollback(tmp_path):
    c = compiled()
    p = initial(c.problem)
    for target in [-1e-5, -2e-5]:
        s = solve(
            c.problem, p, control_global_dof=7, target_control_displacement_m=target
        )
        assert s.committed
        p = s.accepted_checkpoint
    raw = dump(c.problem, p)
    assert dump(c.problem, load(raw, c.problem)) == raw
    with pytest.raises(ValueError):
        load(raw, compiled(False).problem)
    (tmp_path / "checkpoint.json").write_bytes(raw)
    expected = solve(
        c.problem, p, control_global_dof=7, target_control_displacement_m=-1e-5
    )
    assert expected.committed
    script = """
import importlib.util,sys,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('rational_tests',Path(sys.argv[1])/'tests/test_rc_control_rational_accumulation.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=m.compiled();r=Path(sys.argv[2]);p=m.load((r/'checkpoint.json').read_bytes(),c.problem)
s=m.solve(c.problem,p,control_global_dof=7,target_control_displacement_m=-1e-5);assert s.committed
(r/'step.json').write_text(json.dumps(s.to_dict()))
"""
    proc = subprocess.run(
        [sys.executable, "-B", "-c", script, str(ROOT), str(tmp_path)],
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads((tmp_path / "step.json").read_text()) == expected.to_dict()
    fail = solve(
        c.problem,
        p,
        control_global_dof=7,
        target_control_displacement_m=-0.01,
        config=StatefulFiberFrame2DDisplacementControlConfig(
            newton=NewtonRaphsonConfig(max_iterations=1)
        ),
    )
    assert (
        not fail.committed
        and fail.metrics["rollback_exact"]
        and dump(c.problem, p) == raw
    )


def test_cyclic_original_recovery_and_mixed_member_rejection(tmp_path):
    path = tmp_path / "study"
    r = benchmark_rc_control_seed_paths(
        load_neutral_json(MODEL),
        BoundedRCFiberDirectControlRequest(
            7, (-1e-5, -2e-5, -1e-5), allow_reversals=True, maximum_reversals=1
        ),
        source_revision="0" * 40,
        output_directory=path,
        strain_evaluation="exact-rational",
        coordinate_precision="twofold-increment",
        material_arithmetic="retained-strain",
        fiber_strain_evaluation="retained-coordinate",
        force_accumulation="rational",
    )
    assert r["reference_repeat_exact"] and r["all_execution_work_reported"]
    for arm in ["reference", "secant", "fresh-reference"]:
        p = json.loads((path / arm / "path.json").read_text())
        assert p["status"] == "complete" and p["accepted_target_count"] == 3
    new, old = compiled(), compiled(False)
    with pytest.raises(ValueError, match="one supported force accumulation"):
        replace(new.problem, members=(new.problem.members[0], old.problem.members[1]))
