"""Focused verification for the bounded global corotational 3D frame path."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.assembly.corotational_frame3d_global import (
    COROTATIONAL_FRAME3D_GLOBAL_CHECKPOINT_SCHEMA_VERSION,
    COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
    CorotationalFrame3DGlobalConfig,
    CorotationalFrame3DGlobalError,
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
    assemble_corotational_frame3d_global,
    initial_corotational_frame3d_global_checkpoint,
    solve_corotational_frame3d_global_load_path,
    validate_corotational_frame3d_global_checkpoint,
)
from structural_analysis.elements.frame3d import FrameProps
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
    local_timoshenko_frame_stiffness,
)


ROOT = Path(__file__).resolve().parents[1]


def _section() -> TimoshenkoFrame3DSection:
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=0.02,
            e_n_per_m2=2.0e8,
            g_n_per_m2=8.0e7,
            iy_m4=5.0e-5,
            iz_m4=8.0e-5,
            j_m4=1.0e-5,
        ),
        effective_shear_area_y_m2=0.015,
        effective_shear_area_z_m2=0.012,
    )


def _cantilever_model(
    *, load_kn: float = 1.0, model_id: str = "cantilever"
) -> CorotationalFrame3DModel:
    reference_load = [0.0] * 12
    reference_load[7] = load_kn
    return CorotationalFrame3DModel(
        node_coordinates_m=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        members=(CorotationalFrame3DMember("member-1", 0, 1, _section()),),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(reference_load),
        model_id=model_id,
    )


def _two_element_model() -> CorotationalFrame3DModel:
    reference_load = [0.0] * 18
    reference_load[13] = 0.1
    section = _section()
    return CorotationalFrame3DModel(
        node_coordinates_m=(
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (4.0, 0.0, 0.0),
        ),
        members=(
            CorotationalFrame3DMember("member-1", 0, 1, section),
            CorotationalFrame3DMember("member-2", 1, 2, section),
        ),
        restrained_dofs=tuple(range(6)),
        reference_load_kn=tuple(reference_load),
        model_id="two-element-cantilever",
    )


def test_global_assembly_scatters_two_members_in_shared_dof_space() -> None:
    model = _two_element_model()
    assembly = assemble_corotational_frame3d_global(
        model,
        np.zeros(model.total_dofs),
    )
    element = local_timoshenko_frame_stiffness(_section(), 2.0)
    reference = np.zeros((18, 18), dtype=np.float64)
    first = tuple(range(12))
    second = tuple(range(6, 18))
    reference[np.ix_(first, first)] += element
    reference[np.ix_(second, second)] += element

    np.testing.assert_allclose(assembly.tangent, reference, rtol=5.0e-8, atol=0.1)
    assert np.linalg.norm(assembly.internal_force, ord=np.inf) <= 1.0e-8
    assert len(assembly.member_responses) == 2
    assert assembly.displacement.flags.writeable is False
    assert assembly.internal_force.flags.writeable is False
    assert assembly.tangent.flags.writeable is False


def test_global_cantilever_matches_timoshenko_closed_form_and_recovers_reactions() -> (
    None
):
    model = _cantilever_model()
    config = CorotationalFrame3DGlobalConfig()
    solution = solve_corotational_frame3d_global_load_path(
        model,
        (0.25, 0.5, 1.0),
        config=config,
    )
    terminal = solution.steps[-1]
    displacement_y = solution.final_checkpoint.displacement[7]
    props = _section().frame
    expected = 1.0 * 2.0**3 / (3.0 * props.e_n_per_m2 * props.iz_m4) + 1.0 * 2.0 / (
        props.g_n_per_m2 * _section().effective_shear_area_y_m2
    )
    reactions = dict(terminal.reactions)

    assert displacement_y == pytest.approx(expected, rel=1.0e-7, abs=1.0e-12)
    assert reactions[1] == pytest.approx(-1.0, rel=1.0e-8, abs=1.0e-8)
    assert reactions[5] == pytest.approx(-2.0, rel=1.0e-8, abs=1.0e-8)
    assert terminal.free_residual_inf_norm_kn <= 2.0e-8
    assert terminal.relative_residual <= 2.0e-8
    assert len(terminal.members) == 1
    assert terminal.members[0].current_length_m > terminal.members[0].initial_length_m
    assert terminal.members[0].strain_energy_kn_m > 0.0
    assert solution.regularization_used is False
    assert solution.fallback_used is False
    assert solution.contract_pass is True


def test_two_element_global_path_uses_both_members_and_reaches_equilibrium() -> None:
    model = _two_element_model()
    result = solve_corotational_frame3d_global_load_path(
        model,
        (1.0,),
        config=CorotationalFrame3DGlobalConfig(),
    )
    props = _section().frame
    expected = 0.1 * 4.0**3 / (3.0 * props.e_n_per_m2 * props.iz_m4) + 0.1 * 4.0 / (
        props.g_n_per_m2 * _section().effective_shear_area_y_m2
    )
    terminal = result.steps[0]

    assert result.final_checkpoint.displacement[13] == pytest.approx(
        expected,
        rel=1.0e-7,
        abs=1.0e-12,
    )
    assert len(terminal.members) == 2
    assert dict(terminal.reactions)[1] == pytest.approx(-0.1, abs=2.0e-9)
    assert dict(terminal.reactions)[5] == pytest.approx(-0.4, abs=3.0e-9)
    assert terminal.free_residual_inf_norm_kn <= 2.0e-8


def test_checkpoint_resume_is_byte_exact_and_schema_valid() -> None:
    model = _cantilever_model()
    config = CorotationalFrame3DGlobalConfig()
    one_shot = solve_corotational_frame3d_global_load_path(
        model,
        (0.5, 1.0),
        config=config,
    )
    prefix = solve_corotational_frame3d_global_load_path(
        model,
        (0.5,),
        config=config,
    )
    resumed = solve_corotational_frame3d_global_load_path(
        model,
        (1.0,),
        config=config,
        resume_from=prefix.final_checkpoint,
    )

    assert one_shot.final_checkpoint == resumed.final_checkpoint
    assert (
        one_shot.final_checkpoint.checkpoint_hash
        == resumed.final_checkpoint.checkpoint_hash
    )
    assert one_shot.steps[-1].members == resumed.steps[-1].members
    assert (
        one_shot.result_hash
        == solve_corotational_frame3d_global_load_path(
            model,
            (0.5, 1.0),
            config=config,
        ).result_hash
    )

    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/"
            "corotational_frame3d_global_checkpoint_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(one_shot.final_checkpoint.to_dict())
    assert (
        one_shot.final_checkpoint.schema_version
        == COROTATIONAL_FRAME3D_GLOBAL_CHECKPOINT_SCHEMA_VERSION
    )
    assert one_shot.final_checkpoint.profile == COROTATIONAL_FRAME3D_GLOBAL_PROFILE


def test_checkpoint_tamper_and_cross_model_resume_fail_closed() -> None:
    model = _cantilever_model()
    config = CorotationalFrame3DGlobalConfig()
    checkpoint = solve_corotational_frame3d_global_load_path(
        model,
        (0.5,),
        config=config,
    ).final_checkpoint
    tampered_values = list(checkpoint.displacement)
    tampered_values[7] += 1.0e-4
    tampered = replace(checkpoint, displacement=tuple(tampered_values))

    with pytest.raises(CorotationalFrame3DGlobalError, match="hash mismatch"):
        validate_corotational_frame3d_global_checkpoint(
            tampered,
            model=model,
            config=config,
        )
    with pytest.raises(CorotationalFrame3DGlobalError, match="binding"):
        validate_corotational_frame3d_global_checkpoint(
            checkpoint,
            model=_cantilever_model(model_id="different-model"),
            config=config,
        )


def test_singular_supports_and_invalid_load_history_never_fallback() -> None:
    base = _cantilever_model()
    underconstrained = CorotationalFrame3DModel(
        node_coordinates_m=base.node_coordinates_m,
        members=base.members,
        restrained_dofs=(0, 1, 2),
        reference_load_kn=base.reference_load_kn,
        model_id="underconstrained",
    )
    config = CorotationalFrame3DGlobalConfig()

    with pytest.raises(CorotationalFrame3DGlobalError, match="singular|conditioning"):
        solve_corotational_frame3d_global_load_path(
            underconstrained,
            (1.0,),
            config=config,
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        solve_corotational_frame3d_global_load_path(
            base,
            (0.5, 0.5),
            config=config,
        )
    initial = initial_corotational_frame3d_global_checkpoint(base, config=config)
    assert initial.load_factor == 0.0
    assert initial.parent_checkpoint_hash is None
