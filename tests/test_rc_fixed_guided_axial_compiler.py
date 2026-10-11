"""Ideal support verification; no TC11 fixture or material calibration claim."""

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile, _reaction_rows
from structural_analysis.assembly.stateful_fiber_frame2d import (
    assemble_stateful_fiber_frame2d,
)
from structural_analysis.assembly.stateful_fiber_frame2d_control_path import (
    run_stateful_fiber_frame2d_control_path as run,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def fixture(axis=0, segments=1, swap=False):
    data = json.loads(
        (
            Path(__file__).parents[1]
            / "examples/public_rc_fiber_frame_explicit_layers.json"
        ).read_text()
    )
    data["nodes"] = [
        {
            "id": f"N{i}",
            "coordinates": [
                3.0 * i / segments if axis == 0 else 0.0,
                3.0 * i / segments if axis == 1 else 0.0,
                0.0,
            ],
        }
        for i in range(segments + 1)
    ]
    data["elements"] = [
        dict(data["elements"][0], id=f"M{i}", nodes=[f"N{i}", f"N{i + 1}"])
        for i in range(segments)
    ]
    fixed, guided = (f"N{segments}", "N0") if swap else ("N0", f"N{segments}")
    data["supports"] = [
        {"node": fixed, "dofs": ["UX", "UY", "RZ"]},
        {"node": guided, "dofs": ["UY" if axis == 0 else "UX", "RZ"]},
    ]
    data["loads"] = [
        {
            "node": guided,
            "components": dict(
                FX=float(axis == 0), FY=float(axis == 1), FZ=0.0, MX=0.0, MY=0.0, MZ=0.0
            ),
        }
    ]
    # Symmetric mixed-material reinforcement keeps the independent EA/L oracle
    # free of axial/bending coupling, even with interior nodes.
    layer = data["sections"][0]["steel_layers"][0]
    data["sections"][0]["steel_layers"] = [
        dict(layer, id=f"L{i}", y_m=y, steel_material=material)
        for i, (y, material) in enumerate(
            [(-0.25, "steel"), (-0.15, "hanger"), (0.15, "hanger"), (0.25, "steel")]
        )
    ]
    return data


def compile_model(data, **kwargs):
    return _compile(
        load_neutral_json_bytes(json.dumps(data).encode()).detached_analysis_snapshot(),
        **kwargs,
    )


@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize("segments", [1, 3])
@pytest.mark.parametrize("swap", [False, True])
def test_axial_stiffness_reactions_reversals_and_restart(axis, segments, swap):
    data = fixture(axis, segments, swap)
    compiled, blockers, _ = compile_model(data, experimental_fixed_guided_axial=True)
    assert not blockers
    problem = compiled.problem
    controlled = axis if swap else 3 * segments + axis
    fixed_axial = 3 * segments + axis if swap else axis
    targets = (1e-6, 2e-6, -1e-6, -2e-6, 1e-6)
    options = dict(
        control_global_dof=controlled, allow_reversals=True, maximum_reversals=4
    )
    whole = run(problem, targets, **options)
    prefix = run(problem, targets[:2], **options)
    resumed = run(problem, targets[2:], restart=prefix.restart_artifact(), **options)
    assert whole.status == "ready"
    assert (
        whole.final_checkpoint.canonical_bytes()
        == resumed.final_checkpoint.canonical_bytes()
    )
    sec = data["sections"][0]
    materials = {m["id"]: m for m in data["materials"]}
    ea = (
        sec["width_m"]
        * sec["depth_m"]
        * materials[sec["concrete_material"]]["elastic_modulus_mpa"]
    )
    ea += sum(
        layer["bar_count"]
        * layer["bar_area_m2"]
        * materials[layer["steel_material"]]["elastic_modulus_mpa"]
        for layer in sec["steel_layers"]
    )
    for step, target in zip(whole.steps, targets):
        assert step.committed
        child = step.accepted_checkpoint
        expected = ea * 1000 * target / 3.0
        assert child.load_factor == pytest.approx(expected, rel=1e-10, abs=1e-10)
        displacements = np.array(child.global_displacements)
        assert np.all(displacements[list(problem.fixed_global_dofs)] == 0.0)
        assembly = assemble_stateful_fiber_frame2d(
            problem,
            step.parent_checkpoint,
            target_load_factor=child.load_factor,
            trial_free_coordinates_m=(
                displacements / problem.physical_coordinate_scale
            )[list(problem.free_global_dofs)],
        )
        assert assembly.reactions_global[fixed_axial] == pytest.approx(
            -expected, rel=1e-10, abs=1e-10
        )
        assert np.max(np.abs(assembly.residual_kn)) < 1e-8
        canonical_reactions = np.zeros(6 * len(data["nodes"]))
        for i in range(len(data["nodes"])):
            canonical_reactions[6 * i : 6 * i + 2] = assembly.reactions_global[
                3 * i : 3 * i + 2
            ]
            canonical_reactions[6 * i + 5] = assembly.reactions_global[3 * i + 2]
        rows = _reaction_rows(compiled, canonical_reactions)
        assert len(rows) == 5
        assert (data["loads"][0]["node"], ("UX", "UY")[axis]) not in {
            (r["node_id"], r["dof"]) for r in rows
        }
    changed = deepcopy(data)
    changed["supports"] = [changed["supports"][0]]
    legacy, blockers, _ = compile_model(changed)
    assert not blockers
    with pytest.raises(ValueError):
        run(legacy.problem, targets[2:], restart=prefix.restart_artifact(), **options)


@pytest.mark.parametrize(
    "mutation",
    [
        "inclined",
        "folded",
        "duplicate_station",
        "interior_support",
        "duplicate_support",
        "two_fixed",
        "two_guided",
        "wrong_guide",
        "duplicate_dof",
        "nonstring_dof",
        "rotation_free",
        "support_count",
        "fixed_load",
        "guided_transverse_load",
        "guided_moment",
    ],
)
def test_invalid_boundary_rejected_before_solve(mutation):
    data = fixture(segments=3)
    if mutation == "inclined":
        data["nodes"][1]["coordinates"][1] = 0.1
    elif mutation == "folded":
        data["nodes"][1]["coordinates"][0] = 2.5
    elif mutation == "duplicate_station":
        data["nodes"][2]["coordinates"][0] = 0.0
    elif mutation == "interior_support":
        data["supports"][1]["node"] = "N1"
    elif mutation == "duplicate_support":
        data["supports"][1]["node"] = "N0"
    elif mutation == "two_fixed":
        data["supports"][1]["dofs"] = ["UX", "UY", "RZ"]
    elif mutation == "two_guided":
        data["supports"][0]["dofs"] = ["UY", "RZ"]
    elif mutation == "wrong_guide":
        data["supports"][1]["dofs"] = ["UX", "RZ"]
    elif mutation == "duplicate_dof":
        data["supports"][1]["dofs"] = ["UY", "RZ", "RZ"]
    elif mutation == "nonstring_dof":
        data["supports"][1]["dofs"] = [["UY"], "RZ"]
    elif mutation == "rotation_free":
        data["supports"][1]["dofs"] = ["UY"]
    elif mutation == "support_count":
        data["supports"].pop()
    elif mutation == "fixed_load":
        data["loads"][0]["node"] = "N0"
    elif mutation == "guided_transverse_load":
        data["loads"][0]["components"]["FY"] = 1.0
    elif mutation == "guided_moment":
        data["loads"][0]["components"]["MZ"] = 1.0
    compiled, blockers, _ = compile_model(data, experimental_fixed_guided_axial=True)
    assert compiled is None and blockers


def test_explicit_exclusive_opt_in_and_default_rejection():
    data = fixture()
    assert compile_model(data)[0] is None
    for value in (1, "true", None):
        with pytest.raises(ValueError):
            compile_model(data, experimental_fixed_guided_axial=value)
    with pytest.raises(ValueError):
        compile_model(
            data,
            experimental_fixed_guided_axial=True,
            experimental_pin_roller_beam=True,
        )


@pytest.mark.parametrize("axis", [0, 1])
def test_nonlinear_material_reversal_restart_and_failed_step_rollback(axis):
    from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
        StatefulFiberFrame2DDisplacementControlConfig,
        solve_stateful_fiber_frame2d_displacement_control_step,
    )
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    compiled, blockers, _ = compile_model(
        fixture(axis), experimental_fixed_guided_axial=True
    )
    assert not blockers
    problem = compiled.problem
    config = StatefulFiberFrame2DDisplacementControlConfig(
        initial_guess="control_target"
    )
    options = dict(
        control_global_dof=3 + axis,
        allow_reversals=True,
        maximum_reversals=4,
        config=config,
    )
    targets = (0.0003, 0.0015, 0.0045, 0.009, 0.003, -0.0015, -0.006, 0.0, 0.006)
    whole = run(problem, targets, **options)
    assert whole.status == "ready"
    prefix = run(problem, targets[:4], **options)
    resumed = run(problem, targets[4:], restart=prefix.restart_artifact(), **options)
    assert (
        resumed.final_checkpoint.canonical_bytes()
        == whole.final_checkpoint.canonical_bytes()
    )
    assert resumed.restart_artifact() == whole.restart_artifact()
    parent = prefix.final_checkpoint
    original = parent.canonical_bytes()
    failed = solve_stateful_fiber_frame2d_displacement_control_step(
        problem,
        parent,
        control_global_dof=3 + axis,
        target_control_displacement_m=targets[4],
        config=StatefulFiberFrame2DDisplacementControlConfig(
            initial_guess="control_target", newton=NewtonRaphsonConfig(max_iterations=0)
        ),
    )
    assert not failed.committed
    assert (
        original
        == parent.canonical_bytes()
        == failed.accepted_checkpoint.canonical_bytes()
    )
    states = []

    def visit(value):
        if isinstance(value, dict):
            if "plastic_strain" in value or "tensile_damage" in value:
                states.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(whole.final_checkpoint.to_dict())
    for key in ("accumulated_plastic_strain", "tensile_damage", "compressive_damage"):
        assert max(float(state.get(key, 0.0)) for state in states) > 0.0
