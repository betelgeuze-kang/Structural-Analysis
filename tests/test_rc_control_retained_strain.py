"""Retained trial strain changes stress precision, not native state authority."""

from decimal import Decimal, localcontext, ROUND_DOWN
from fractions import Fraction as F
import importlib.util
import json
import math
from pathlib import Path
import os
import subprocess
import sys

import numpy as np
import pytest

from structural_analysis.materials.retained_fiber_strain import (
    RetainedStrainSteel,
    RetainedStrainConcrete,
    RETAINED_FIBER_PROFILE,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.trial_runtime import MaterialTrialRuntimeRecorder
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_material_arithmetic,
    _with_fiber_strain_evaluation,
    _with_coordinate_precision,
    _with_strain_evaluation,
    benchmark_rc_control_seed_paths,
)
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
            "retained-strain",
        ),
        "retained-coordinate",
    )


def test_steel_retains_elastic_stress_below_float_input_spacing():
    law = RetainedStrainSteel()
    base = BilinearCombinedHardeningSteel()
    parent = base.integrate(0.01, base.initial_state()).state
    x = F(parent.plastic_strain) + F(math.ulp(parent.plastic_strain)) / 4
    assert float(x) == parent.plastic_strain
    result = law.integrate(x, parent)
    original = base.integrate(float(x), parent)
    assert not result.yielded and original.stress_mpa == 0
    assert (
        result.stress_mpa
        == float(F(law.elastic_modulus_mpa) * (x - F(parent.plastic_strain)))
        > 0
    )
    assert result.state.canonical_bytes() == original.state.canonical_bytes()


@pytest.mark.parametrize("kind", ["steel", "concrete"])
def test_cyclic_native_updates_and_original_branch_decisions_are_preserved(kind):
    base = (
        BilinearCombinedHardeningSteel()
        if kind == "steel"
        else AsymmetricConcreteDamageMaterial()
    )
    law = RetainedStrainSteel() if kind == "steel" else RetainedStrainConcrete()
    parent = base.initial_state()
    for rounded in [-0.0001, -0.003, 0.007, 0.002, -0.004, 0.001, 0.0]:
        x = F(rounded) + F(math.ulp(rounded)) / 4
        raw = parent.canonical_bytes()
        a = base.integrate(float(x), parent)
        b = law.integrate(x, parent)
        assert (
            a.state.canonical_bytes() == b.state.canonical_bytes()
            and parent.canonical_bytes() == raw
        )
        keys = (
            ["yielded", "plastic_multiplier_increment"]
            if kind == "steel"
            else ["active_branch", "active_damage", "damage_evolved"]
        )
        assert all(a.to_dict()[k] == b.to_dict()[k] for k in keys)
        record = b.to_dict()
        assert record["stress_trial_strain"] == {
            "numerator": str(x.numerator),
            "denominator": str(x.denominator),
        }
        assert record["stress_evaluation_profile"] == RETAINED_FIBER_PROFILE
        parent = b.state


@pytest.mark.parametrize("strain", [0.00001, 0.001, -0.003, -1.0])
def test_concrete_stress_matches_independent_100_digit_expression(strain):
    law = RetainedStrainConcrete()
    parent = law.initial_state()
    x = F(strain) + F(math.ulp(strain)) / 4
    actual = law.integrate(x, parent)
    with localcontext() as context:
        context.prec = 100

        def D(value):
            f = F(value)
            return Decimal(f.numerator) / Decimal(f.denominator)

        threshold = (
            law.tensile_threshold_strain
            if strain >= 0
            else law.compressive_threshold_strain
        )
        rate = (
            law.tensile_softening_rate
            if strain >= 0
            else law.compressive_softening_rate
        )
        history = abs(D(x))
        survival = (
            Decimal(1)
            if abs(float(x)) <= threshold
            else D(threshold) / history * ((D(threshold) - history) * D(rate)).exp()
        )
        expected = float(
            D(law.elastic_modulus_mpa)
            * max(survival, D(1 - math.nextafter(1.0, 0.0)))
            * D(x)
        )
    assert actual.stress_mpa == expected
    with localcontext() as context:
        context.prec = 7
        context.rounding = ROUND_DOWN
        assert law.integrate(x, parent).to_dict() == actual.to_dict()


@pytest.mark.parametrize("scale", [0.05, 1.0, 4.0])
def test_same_parent_element_tangent_and_timing_coverage(scale):
    e = compiled().problem.members[0].element
    p = e.initial_state()
    u = np.array([0.0, 0.0, 0.0, 1e-4, -0.001, 0.0002]) * scale
    low = np.zeros(6)
    recorder = MaterialTrialRuntimeRecorder()
    r = e.integrate(
        u, p, local_displacement_compensation=low, material_runtime=recorder
    )
    assert (
        recorder.coverage_complete
        and recorder.call_count == len(e.section.fibers) * e.integration_order
    )
    assert (
        e.integrate(u, p, local_displacement_compensation=low).to_dict() == r.to_dict()
    )
    h = 1e-8
    columns = []
    for j in range(6):
        d = np.zeros(6)
        d[j] = h
        a = e.integrate(u + d, p, local_displacement_compensation=low)
        b = e.integrate(u - d, p, local_displacement_compensation=low)
        columns.append((a.internal_force_local - b.internal_force_local) / (2 * h))
    K = np.array(columns).T
    assert (
        np.linalg.norm(K - r.consistent_tangent_local, np.inf)
        / np.linalg.norm(K, np.inf)
        < 2e-5
    )


def test_fresh_native_restart_mixed_profile_rejection_and_failure_rollback(tmp_path):
    problem = compiled().problem
    parent = initial(problem)
    for target in [-1e-5, -2e-5]:
        s = solve(
            problem, parent, control_global_dof=7, target_control_displacement_m=target
        )
        assert s.committed
        parent = s.accepted_checkpoint
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
spec=importlib.util.spec_from_file_location('retained_test',Path(sys.argv[1])/'tests/test_rc_control_retained_strain.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=m.compiled().problem;r=Path(sys.argv[2]);parent=m.load((r/'checkpoint.json').read_bytes(),p)
s=m.solve(p,parent,control_global_dof=7,target_control_displacement_m=-1e-5);assert s.committed
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
    old, b, _ = _compile(load_neutral_json(MODEL))
    assert not b
    old = _with_fiber_strain_evaluation(
        _with_material_arithmetic(
            _with_coordinate_precision(
                _with_strain_evaluation(old, "exact-rational"), "twofold-increment"
            ),
            "stable-stress",
        ),
        "direct-coordinate",
    )
    with pytest.raises(ValueError):
        load(raw, old.problem)
    fail = solve(
        problem,
        parent,
        control_global_dof=7,
        target_control_displacement_m=-0.01,
        config=StatefulFiberFrame2DDisplacementControlConfig(
            newton=NewtonRaphsonConfig(max_iterations=1)
        ),
    )
    assert (
        not fail.committed
        and fail.metrics["rollback_exact"]
        and dump(problem, parent) == raw
    )


def test_full_cyclic_original_recovery_and_saved_force_replay(tmp_path):
    path = tmp_path / "study"
    report = benchmark_rc_control_seed_paths(
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
    )
    assert report["reference_repeat_exact"] and report["all_execution_work_reported"]
    for arm in ["reference", "secant", "fresh-reference"]:
        p = json.loads((path / arm / "path.json").read_text())
        assert p["status"] == "complete" and p["accepted_target_count"] == 3
    spec = importlib.util.spec_from_file_location(
        "force", ROOT / "scripts/diagnose_rc_control_force_error.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.diagnose(path)["target_count"] == 3


@pytest.mark.parametrize("law", [RetainedStrainSteel(), RetainedStrainConcrete()])
def test_rounded_only_input_is_rejected(law):
    with pytest.raises(ValueError, match="requires original rational"):
        law.integrate(0.001, law.initial_state())


@pytest.mark.parametrize(
    "material,fiber",
    [("retained-strain", "generalized"), ("stable-stress", "retained-coordinate")],
)
def test_incompatible_retained_profiles_fail_before_output_creation(
    tmp_path, material, fiber
):
    output = tmp_path / "unexpected"
    with pytest.raises(ValueError, match="retained strain requires paired"):
        benchmark_rc_control_seed_paths(
            load_neutral_json(MODEL),
            BoundedRCFiberDirectControlRequest(7, (-1e-5,)),
            source_revision="0" * 40,
            output_directory=output,
            strain_evaluation="exact-rational",
            material_arithmetic=material,
            fiber_strain_evaluation=fiber,
        )
    assert not output.exists()


def test_retained_section_hash_binds_original_base_identity_without_intermediate_profiles():
    from structural_analysis.engine_v2.contracts._canonical import canonical_hash
    from structural_analysis.materials.stateful_fiber_section import (
        StatefulRCFiberSection,
    )

    section = compiled().problem.members[0].element.section
    original = StatefulRCFiberSection(
        fibers=section.fibers,
        steel=section.steel,
        concrete=section.concrete,
        section_id=section.section_id,
    )
    expected = canonical_hash(
        {
            "base_section_contract_hash": original.contract_hash,
            "fiber_strain_evaluation": RETAINED_FIBER_PROFILE,
            "concrete_decimal_precision": 80,
        }
    )
    assert section.contract_hash == expected
    assert section.initial_state().section_contract_hash == expected
