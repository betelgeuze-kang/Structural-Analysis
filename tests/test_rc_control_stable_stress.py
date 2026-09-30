"""Stable trial stresses keep original state updates and full native authority."""

from dataclasses import asdict, replace
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import os
import subprocess
import sys

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
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_material_arithmetic,
    _with_coordinate_precision,
    _with_strain_evaluation,
    benchmark_rc_control_seed_paths,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.materials.stable_stress import (
    StableStressSteel,
    StableStressConcrete,
    STABLE_STRESS_PROFILE,
    stable_stress_section,
)
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section
from structural_analysis.io.neutral.loader import load_neutral_json

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"


@pytest.mark.parametrize("kind", ["steel", "concrete"])
def test_original_branch_and_native_state_update_are_exact_for_same_inputs(kind):
    base = (
        BilinearCombinedHardeningSteel()
        if kind == "steel"
        else AsymmetricConcreteDamageMaterial()
    )
    stable = (
        StableStressSteel(**asdict(base))
        if kind == "steel"
        else StableStressConcrete(**asdict(base))
    )
    parent = base.initial_state()
    for strain in [-0.0001, -0.003, 0.007, 0.002, -0.004, 0.001, 0.0]:
        before = parent.canonical_bytes()
        expected = base.integrate(strain, parent)
        actual = stable.integrate(strain, parent)
        assert expected.state.canonical_bytes() == actual.state.canonical_bytes()
        assert parent.canonical_bytes() == before
        assert actual.committed_state_hash == expected.committed_state_hash
        if kind == "steel":
            assert actual.yielded == expected.yielded
            assert (
                actual.plastic_multiplier_increment
                == expected.plastic_multiplier_increment
            )
        else:
            assert actual.active_branch == expected.active_branch
            assert actual.active_damage == expected.active_damage
            assert actual.damage_evolved == expected.damage_evolved
        assert actual.to_dict()["stress_evaluation_profile"] == STABLE_STRESS_PROFILE
        assert "stress_evaluation_profile" not in expected.to_dict()
        parent = actual.state


def test_survival_stress_avoids_damage_complement_cancellation():
    material = StableStressConcrete()
    parent = material.initial_state()
    strain = 0.007
    result = material.integrate(strain, parent)
    legacy = AsymmetricConcreteDamageMaterial().integrate(strain, parent)
    survival = (
        material.tensile_threshold_strain
        / strain
        * math.exp(
            -material.tensile_softening_rate
            * (strain - material.tensile_threshold_strain)
        )
    )
    with localcontext() as ctx:
        ctx.prec = 90
        expected = float(
            Decimal.from_float(survival)
            * Decimal.from_float(material.elastic_modulus_mpa)
            * Decimal.from_float(strain)
        )
    assert result.stress_mpa == expected and legacy.stress_mpa != expected
    assert result.state.canonical_bytes() == legacy.state.canonical_bytes()


def test_original_damage_cap_and_underflow_branch_are_retained():
    material = StableStressConcrete()
    result = material.integrate(1.0, material.initial_state())
    assert result.active_damage == math.nextafter(1.0, 0.0)
    assert (
        result.stress_mpa
        == (1.0 - math.nextafter(1.0, 0.0)) * material.elastic_modulus_mpa
    )
    assert result.consistent_tangent_mpa == result.stress_mpa


@pytest.mark.parametrize(
    "kind,strain,parent_strain",
    [
        ("steel", 0.004, 0),
        ("steel", -0.001, 0.003),
        ("concrete", 0.001, 0),
        ("concrete", 0.0005, 0.003),
        ("concrete", -0.003, 0),
    ],
)
def test_stable_tangent_matches_same_parent_finite_difference(
    kind, strain, parent_strain
):
    material = StableStressSteel() if kind == "steel" else StableStressConcrete()
    parent = material.integrate(parent_strain, material.initial_state()).state
    result = material.integrate(strain, parent)
    eps = 1e-8
    derivative = (
        material.integrate(strain + eps, parent).stress_mpa
        - material.integrate(strain - eps, parent).stress_mpa
    ) / (2 * eps)
    assert derivative == pytest.approx(
        result.consistent_tangent_mpa, rel=2e-6, abs=1e-7
    )


def test_section_profile_changes_contract_and_rejects_default_native_parent():
    base = make_rectangular_stateful_rc_fiber_section()
    stable = stable_stress_section(base)
    assert asdict(base.steel) == asdict(stable.steel) and asdict(
        base.concrete
    ) == asdict(stable.concrete)
    assert base.contract_hash != stable.contract_hash
    with pytest.raises(ValueError, match="section_contract_hash"):
        stable.integrate([0, 0], base.initial_state())
    with pytest.raises(ValueError, match="both explicit stable"):
        replace(stable, steel=base.steel)


def _problem():
    compiled, blockers, _ = _compile(load_neutral_json(MODEL))
    assert not blockers
    return _with_material_arithmetic(
        _with_coordinate_precision(
            _with_strain_evaluation(compiled, "exact-rational"), "twofold-increment"
        ),
        "stable-stress",
    ).problem


def test_native_checkpoint_reopens_with_stable_profile_and_continues_in_fresh_process(
    tmp_path,
):
    problem = _problem()
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
import json,sys
from pathlib import Path
from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.benchmark.rc_control_seed_runtime import _with_material_arithmetic,_with_coordinate_precision,_with_strain_evaluation
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import load_stateful_fiber_frame2d_checkpoint_bytes as load
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import solve_stateful_fiber_frame2d_displacement_control_step as solve
compiled,blockers,_=_compile(load_neutral_json(Path(sys.argv[1])));assert not blockers
p=_with_material_arithmetic(_with_coordinate_precision(_with_strain_evaluation(compiled,'exact-rational'),'twofold-increment'),'stable-stress').problem
r=Path(sys.argv[2]);parent=load((r/'checkpoint.json').read_bytes(),p)
step=solve(p,parent,control_global_dof=7,target_control_displacement_m=-1e-5);assert step.committed
(r/'step.json').write_text(json.dumps(step.to_dict()))
"""
    proc = subprocess.run(
        [sys.executable, "-B", "-c", script, str(MODEL), str(tmp_path)],
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads((tmp_path / "step.json").read_text()) == expected.to_dict()
    default, _, _ = _compile(load_neutral_json(MODEL))
    with pytest.raises(ValueError):
        load(raw, default.problem)


def test_complete_cyclic_original_recovery_uses_stable_materials(tmp_path):
    request = BoundedRCFiberDirectControlRequest(
        7,
        (-1e-5, -2e-5, -1e-5, 1e-5, 0, -0.5e-5),
        allow_reversals=True,
        maximum_reversals=2,
    )
    report = benchmark_rc_control_seed_paths(
        load_neutral_json(MODEL),
        request,
        source_revision="0" * 40,
        output_directory=tmp_path / "study",
        strain_evaluation="exact-rational",
        coordinate_precision="twofold-increment",
        material_arithmetic="stable-stress",
    )
    assert report["material_arithmetic"] == "stable-stress"
    assert report["reference_repeat_exact"] and report["all_execution_work_reported"]
    for arm in ["reference", "secant", "fresh-reference"]:
        path = json.loads((tmp_path / "study" / arm / "path.json").read_text())
        assert path["status"] == "complete" and path["accepted_target_count"] == 6
        step = json.loads((tmp_path / "study" / arm / "005-1-step.json").read_text())
        assert step["metrics"]["solver_assembly_coordinate_residual_binding_passed"]
        for member in step["trial_assembly"]["member_assemblies"]:
            for section in member["element_response"]["section_responses"]:
                assert all(
                    f["stress_evaluation_profile"] == STABLE_STRESS_PROFILE
                    for f in section["fiber_responses"]
                )

    import importlib.util

    for script in [
        "diagnose_rc_control_section_error.py",
        "diagnose_rc_control_force_error.py",
    ]:
        spec = importlib.util.spec_from_file_location(
            "stable_" + script[:-3], ROOT / "scripts" / script
        )
        diagnostic = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(diagnostic)
        result = diagnostic.diagnose(tmp_path / "study", "secant")
        assert result["target_count"] == 6


@pytest.mark.parametrize("strain", [3.141592653589793, -3.141592653589793])
def test_perfect_plastic_stress_uses_yield_surface_without_large_trial_subtraction(
    strain,
):
    material = StableStressSteel(
        isotropic_hardening_modulus_mpa=0, kinematic_hardening_modulus_mpa=0
    )
    response = material.integrate(strain, material.initial_state())
    assert response.yielded
    assert response.stress_mpa == math.copysign(material.yield_stress_mpa, strain)
    assert response.final_yield_function_mpa == 0


def test_nonconvergent_stable_step_keeps_exact_original_checkpoint():
    from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
        StatefulFiberFrame2DDisplacementControlConfig,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    problem = _problem()
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
    assert not step.committed and step.accepted_checkpoint is parent
    assert step.metrics["rollback_exact"] and parent.canonical_bytes() == raw
