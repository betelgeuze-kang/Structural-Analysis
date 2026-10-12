"""Canonical input bridge tests; synthetic mechanics, not specimen validation."""

from pathlib import Path
import json

import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_corotational_control_model import (
    compile_rc_corotational_control_model,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision import (
    run_corotational_control_subdivision,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    solve_stateful_corotational_fiber_frame2d_load_step,
)
from structural_analysis.io.neutral.loader import (
    load_neutral_json,
    load_neutral_json_bytes,
)


MODEL = (
    Path(__file__).resolve().parents[1]
    / "examples/public_rc_fiber_frame_l_frame_material_history.json"
)


def test_compiler_preserves_authored_sections_geometry_ids_and_separates_loads():
    model = load_neutral_json(MODEL)
    before = model.to_dict()
    small, unsupported, _ = _compile(model)
    assert not unsupported
    compiled = compile_rc_corotational_control_model(
        model, fixed_nodal_loads=(("N3", "FX", -0.01), ("N3", "MZ", 0.02))
    )
    assert model.to_dict() == before
    assert compiled.source_model_checksum == model.canonical_model_checksum
    assert compiled.source_input_checksum == model.input_checksum
    assert compiled.node_ids == small.node_ids
    assert compiled.problem.node_coordinates_m == small.problem.node_coordinates_m
    assert compiled.problem.fixed_global_dofs == small.problem.fixed_global_dofs
    assert (
        compiled.problem.reference_external_loads
        == small.problem.reference_external_loads
    )
    assert compiled.problem.fixed_external_loads == ((6, -0.01), (8, 0.02))
    for original, actual in zip(
        small.problem.members, compiled.problem.members, strict=True
    ):
        assert actual.member_id == original.member_id
        assert (
            actual.element.section.contract_hash
            == original.element.section.contract_hash
        )
        assert actual.element.integration_order == original.element.integration_order
    no_fixed = compile_rc_corotational_control_model(model)
    assert no_fixed.problem.contract_hash != compiled.problem.contract_hash


def test_canonical_model_preload_control_pause_and_reopen():
    compiled = compile_rc_corotational_control_model(
        load_neutral_json(MODEL), fixed_nodal_loads=(("N3", "FX", -0.01),)
    )
    p = compiled.problem
    preload = solve_stateful_corotational_fiber_frame2d_load_step(
        p,
        initial_stateful_corotational_fiber_frame2d_checkpoint(p),
        target_load_factor=0.0,
    )
    assert preload.committed
    targets = (-1e-6, -2e-6, -1.5e-6)
    kwargs = dict(control_global_dof=7, initial_checkpoint=preload.accepted_checkpoint)
    full = run_corotational_control_subdivision(p, targets, **kwargs)
    assert full.contract_pass
    paused = run_corotational_control_subdivision(
        p, targets, attempt_limit_per_call=1, **kwargs
    )
    assert paused.status == "paused"
    # Recompile a freshly read canonical input instead of retaining its objects.
    reopened = compile_rc_corotational_control_model(
        load_neutral_json(MODEL), fixed_nodal_loads=(("N3", "FX", -0.01),)
    )
    resumed = run_corotational_control_subdivision(
        reopened.problem,
        targets,
        control_global_dof=7,
        continuation=paused.continuation,
    )
    assert resumed.contract_pass
    assert resumed.continuation == full.continuation
    changed = compile_rc_corotational_control_model(
        load_neutral_json(MODEL), fixed_nodal_loads=(("N3", "FX", -0.02),)
    )
    with pytest.raises(ValueError, match="input, policy or source mismatch"):
        run_corotational_control_subdivision(
            changed.problem,
            targets,
            control_global_dof=7,
            continuation=paused.continuation,
        )


@pytest.mark.parametrize(
    "loads",
    [
        [],
        (("missing", "FX", 1),),
        (("N3", "FZ", 1),),
        (("N3", "FX", True),),
        (("N3", "FX", float("nan")),),
        (("N3", "FX", 10**400),),
        (("N3", "FX", "1"),),
        (("N3", "FX", 1), ("N3", "FX", 2)),
        (("N3", "FX"),),
    ],
)
def test_compiler_rejects_ambiguous_fixed_loads(loads):
    with pytest.raises(ValueError, match="fixed"):
        compile_rc_corotational_control_model(
            load_neutral_json(MODEL), fixed_nodal_loads=loads
        )


def test_compiler_rejects_unsupported_model_instead_of_losing_semantics():
    payload = json.loads(MODEL.read_text())
    payload["nodes"][1]["coordinates"][2] = 0.5
    model = load_neutral_json_bytes(json.dumps(payload).encode())
    with pytest.raises(ValueError, match="unsupported corotational model input"):
        compile_rc_corotational_control_model(model)
