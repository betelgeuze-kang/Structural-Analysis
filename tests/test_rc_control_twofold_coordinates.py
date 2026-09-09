"""Explicit native coordinate precision; original Newton and recovery authority."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.assembly import (
    stateful_fiber_frame2d_displacement_control as control,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint as initial,
    validate_stateful_fiber_frame2d_checkpoint as validate_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    dump_stateful_fiber_frame2d_checkpoint_bytes as dump,
    load_stateful_fiber_frame2d_checkpoint_bytes as load,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    _with_coordinate_precision,
    _with_strain_evaluation,
    benchmark_rc_control_seed_paths,
)
from structural_analysis.elements.fiber_beam2d_strain import exact_fiber_beam2d_strain
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.solvers.nonlinear import twofold_coordinates as twofold

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"
TARGETS = (-1e-5, -2e-5, -1e-5, 1e-5, 0, -0.5e-5)


def make_problem():
    compiled, blockers, _ = _compile(load_neutral_json(MODEL))
    assert not blockers
    return _with_coordinate_precision(
        _with_strain_evaluation(compiled, "exact-rational"), "twofold-increment"
    ).problem


def solve(problem, parent, target, **kwargs):
    return control.solve_stateful_fiber_frame2d_displacement_control_step(
        problem,
        parent,
        control_global_dof=7,
        target_control_displacement_m=target,
        **kwargs,
    )


@pytest.fixture(scope="module")
def path():
    problem = make_problem()
    parent = initial(problem)
    steps = []
    for target in TARGETS:
        before = parent.canonical_bytes()
        step = solve(problem, parent, target)
        assert step.committed and parent.canonical_bytes() == before
        steps.append(step)
        parent = step.accepted_checkpoint
    assert any(any(s.accepted_checkpoint.free_coordinate_compensation_m) for s in steps)
    return problem, steps


def test_sub_ulp_increment_survives_cancellation_and_coordinate_transform():
    high, low = twofold.add([1.0, 1.0], [0.0, 0.0], [2**-54, 0.0])
    assert high.tolist() == [1.0, 1.0] and low.tolist() == [2**-54, 0.0]
    result, remainder = twofold.transform([[1.0, -1.0]], high, low)
    assert result.tolist() == [2**-54] and remainder.tolist() == [0.0]
    assert not high.flags.writeable and not low.flags.writeable
    local_high = [0.0, 1.0, 0.0, 0.0, 1.0, 0.0]
    local_low = [0.0, 2**-54, 0.0, 0.0, 0.0, 0.0]
    with localcontext() as ctx:
        ctx.prec = 100
        expected = float(-6 * Decimal.from_float(2**-54) / Decimal("2.5") ** 2)
    strain = exact_fiber_beam2d_strain(local_high, 2.5, -1.0, local_low)
    assert strain.tolist() == [0.0, expected]
    assert exact_fiber_beam2d_strain(local_high, 2.5, -1.0).tolist() == [0.0, 0.0]


@pytest.mark.parametrize(
    "high,low",
    [
        ([1.0], [1.0]),
        ([1.0], [-0.0]),
        ([True], [0.0]),
        ([1.0], [False]),
        ([1.0], [np.nan]),
        ([1.0], []),
        ([0.0] * 145, [0.0] * 145),
        ([[0.0]], [[0.0]]),
    ],
)
def test_noncanonical_or_invalid_coordinate_pair_is_rejected(high, low):
    with pytest.raises(ValueError):
        twofold.validate(high, low)


def test_restart_reconstructs_absolute_coordinates_from_native_parent(path, tmp_path):
    problem, steps = path
    parent = steps[1].accepted_checkpoint
    raw = dump(problem, parent)
    restored = load(raw, problem)
    assert dump(problem, restored) == raw
    assert restored.canonical_bytes() == parent.canonical_bytes()
    (tmp_path / "checkpoint.json").write_bytes(raw)
    # Fresh imports and a fresh interpreter: no in-process adapter/cache survives.
    script = """
import json,sys
from pathlib import Path
from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.benchmark.rc_control_seed_runtime import _with_strain_evaluation, _with_coordinate_precision
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import load_stateful_fiber_frame2d_checkpoint_bytes as load, dump_stateful_fiber_frame2d_checkpoint_bytes as dump
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import solve_stateful_fiber_frame2d_displacement_control_step as solve
root=Path(sys.argv[1]); compiled, blockers, _ = _compile(load_neutral_json(Path(sys.argv[2]))); assert not blockers
problem=_with_coordinate_precision(_with_strain_evaluation(compiled,'exact-rational'),'twofold-increment').problem
parent=load((root/'checkpoint.json').read_bytes(),problem)
for i,target in enumerate(json.loads(sys.argv[3])):
    step=solve(problem,parent,control_global_dof=7,target_control_displacement_m=target)
    assert step.committed
    (root/f'{i}-step.json').write_text(json.dumps(step.to_dict(),sort_keys=True))
    parent=step.accepted_checkpoint
(root/'terminal.json').write_bytes(dump(problem,parent))
"""
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            script,
            str(tmp_path),
            str(MODEL),
            json.dumps(TARGETS[2:]),
        ],
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert (tmp_path / "terminal.json").read_bytes() == dump(
        problem, steps[-1].accepted_checkpoint
    )
    for i, step in enumerate(steps[2:]):
        assert json.loads((tmp_path / f"{i}-step.json").read_text()) == step.to_dict()
        adapter = step.trial_solution.problem
        high, low = adapter.absolute_coordinates(
            step.trial_solution.free_displacements_m
        )
        assert high.tolist() == step.metrics["absolute_augmented_coordinates_m"]
        assert (
            low.tolist() == step.metrics["absolute_augmented_coordinate_compensation_m"]
        )
        exact = twofold.fractions(high, low)
        origin = twofold.fractions(*adapter.coordinate_origin())
        # Expansion is the rounded sum of parent + the actual original Newton delta.
        expected = twofold.split(
            a + Fraction(float(d))
            for a, d in zip(
                origin, step.trial_solution.free_displacements_m, strict=True
            )
        )
        assert exact == twofold.fractions(*expected)


@pytest.mark.parametrize(
    "mutation",
    [
        "drop_free",
        "drop_local",
        "boolean",
        "shape",
        "unknown",
        "schema",
        "noncanonical",
        "tamper",
    ],
)
def test_native_codec_rejects_missing_malformed_or_changed_low_parts(path, mutation):
    problem, steps = path
    payload = deepcopy(steps[1].accepted_checkpoint.to_dict())
    if mutation == "drop_free":
        payload.pop("free_coordinate_compensation_m")
    elif mutation == "drop_local":
        payload["element_states"][0].pop("local_displacement_compensation")
    elif mutation == "boolean":
        payload["free_coordinate_compensation_m"][0] = False
    elif mutation == "shape":
        payload["free_coordinate_compensation_m"].pop()
    elif mutation == "unknown":
        payload["unbound_low"] = [0.0]
    elif mutation == "schema":
        payload["schema_version"] = "stateful-fiber-frame2d-checkpoint.v1"
    elif mutation == "noncanonical":
        payload["free_coordinate_compensation_m"][0] = 1.0
    else:
        i = next(
            i for i, v in enumerate(payload["free_coordinate_compensation_m"]) if v
        )
        payload["free_coordinate_compensation_m"][i] = 0.0
    with pytest.raises(ValueError):
        load(json.dumps(payload).encode(), problem)


def test_rehashed_low_tamper_still_fails_native_to_element_binding(path):
    problem, steps = path
    parent = steps[1].accepted_checkpoint
    low = list(parent.free_coordinate_compensation_m)
    i = next(i for i, v in enumerate(low) if v)
    low[i] = 0.0
    changed = replace(parent, free_coordinate_compensation_m=tuple(low), state_hash="")
    assert changed.state_hash != parent.state_hash
    with pytest.raises(ValueError, match="twofold coordinates"):
        validate_checkpoint(problem, changed)
    with pytest.raises(ValueError, match="duplicate key"):
        load(
            dump(problem, parent)[:-1] + b',"free_coordinate_compensation_m":[]}',
            problem,
        )
    compiled, _, _ = _compile(load_neutral_json(MODEL))
    with pytest.raises(ValueError):
        load(dump(problem, parent), compiled.problem)


@pytest.mark.parametrize(
    "field", ["increment_gate_passed", "residual_gate_passed", "free_displacements_m"]
)
def test_forged_newton_result_cannot_commit_and_rolls_back_exactly(
    path, monkeypatch, field
):
    problem, steps = path
    parent = steps[1].accepted_checkpoint
    before = parent.canonical_bytes()
    original = control.newton_raphson_vector

    def forged(*args, **kwargs):
        result = original(*args, **kwargs)
        metrics = dict(result.metrics)
        metrics[field] = (
            [0.0] * len(result.free_displacements_m)
            if field == "free_displacements_m"
            else False
        )
        return replace(result, metrics=metrics)

    monkeypatch.setattr(control, "newton_raphson_vector", forged)
    result = solve(problem, parent, TARGETS[2])
    assert not result.committed and result.accepted_checkpoint is parent
    assert result.metrics["rollback_exact"] and parent.canonical_bytes() == before


def test_profiles_and_invalid_members_are_rejected_before_execution(path, tmp_path):
    problem, _ = path
    for invalid in (None, (None,), []):
        with pytest.raises(ValueError, match="members"):
            replace(problem, members=invalid)
    for invalid in (True, np.array(["a", "b"]), "double-double"):
        with pytest.raises(ValueError, match="coordinate precision"):
            replace(problem.members[0].element, coordinate_precision=invalid)
    with pytest.raises(ValueError, match="frame and member"):
        replace(problem, coordinate_precision="binary64")
    with pytest.raises(ValueError, match="exact-rational"):
        benchmark_rc_control_seed_paths(
            load_neutral_json(MODEL),
            BoundedRCFiberDirectControlRequest(7, (-1e-5,)),
            source_revision="0" * 40,
            output_directory=tmp_path / "invalid",
            coordinate_precision="twofold-increment",
        )
    assert not (tmp_path / "invalid").exists()


def test_complete_seed_paths_keep_original_recovery_and_diagnostic(path, tmp_path):
    request = BoundedRCFiberDirectControlRequest(
        7, TARGETS, allow_reversals=True, maximum_reversals=2
    )
    root = tmp_path / "study"
    report = benchmark_rc_control_seed_paths(
        load_neutral_json(MODEL),
        request,
        source_revision="0" * 40,
        output_directory=root,
        strain_evaluation="exact-rational",
        coordinate_precision="twofold-increment",
    )
    assert report["reference_repeat_exact"] and report["all_execution_work_reported"]
    for arm in ("reference", "secant", "fresh-reference"):
        result = json.loads((root / arm / "path.json").read_text())
        assert result["status"] == "complete" and result["accepted_target_count"] == 6
        for i in range(6):
            step = json.loads((root / arm / f"{i:03d}-1-step.json").read_text())
            assert step["committed"]
            assert step["metrics"]["solver_assembly_coordinate_residual_binding_passed"]
            assert step["metrics"]["coordinate_precision"] == "twofold-increment"
            assert (
                step["trial_solution"]["solver_increment_coordinates_m"]
                == step["trial_solution"]["metrics"]["free_displacements_m"]
            )
    spec = importlib.util.spec_from_file_location(
        "twofold_diagnostic", ROOT / "scripts/diagnose_rc_control_section_error.py"
    )
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    audit = diagnostic.diagnose(root, "secant")
    assert audit["coordinate_precision"] == "twofold-increment"
    for row in audit["rows"]:
        for order in row["orders"].values():
            assert order["components_N_Nm"]["reference_kinematic_evaluation"] == [0, 0]
            assert order["components_N_Nm"]["candidate_kinematic_evaluation"] == [0, 0]


@pytest.mark.parametrize(
    "exact",
    [
        Fraction(1) + Fraction(1, 2**53) + Fraction(1, 2**109),
        -Fraction(1) - Fraction(1, 2**53) - Fraction(1, 2**109),
        -Fraction(1, 2**1100),
    ],
)
def test_split_normalizes_rounded_midpoint_ties_and_underflow(exact):
    high, low = twofold.split([exact])
    twofold.validate(high, low)
    rounded_high = float(exact)
    rounded_low = float(exact - Fraction(rounded_high))
    represented = Fraction(rounded_high) + Fraction(rounded_low)
    assert twofold.fractions(high, low) == [represented]
    assert float(represented) == high[0]
