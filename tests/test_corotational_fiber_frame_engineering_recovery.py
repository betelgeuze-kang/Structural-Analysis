from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_engineering_recovery import (
    CorotationalFiberFrameEngineeringRecoveryError,
    create_corotational_fiber_frame_engineering_result_ir,
    validate_corotational_fiber_frame_engineering_result_ir,
    validate_corotational_fiber_frame_engineering_result_manifest,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_j1_j5 import (
    compile_corotational_fiber_frame_portal_profile,
    create_corotational_fiber_frame_j1_j5_adapter,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    run_stateful_corotational_fiber_frame2d_load_path,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.result_quantity import (
    default_result_quantity_catalog,
)
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section


def _adapter():
    coordinates = ((0.0, 0.0), (4.0, 0.0), (0.0, 3.0), (4.0, 3.0))
    section = make_rectangular_stateful_rc_fiber_section()
    members = tuple(
        StatefulCorotationalFiberFrame2DMember(
            member_id=member_id,
            node_i=node_i,
            node_j=node_j,
            element=StatefulCorotationalFiberBeam2D(
                node_coordinates_m=(coordinates[node_i], coordinates[node_j]),
                section=section,
                integration_order=3,
                element_id=member_id,
            ),
        )
        for member_id, node_i, node_j in (
            ("column-left", 0, 2),
            ("column-right", 1, 3),
            ("beam-top", 2, 3),
        )
    )
    problem = StatefulCorotationalFiberFrame2DProblem(
        case_id="public-corotational-portal",
        node_coordinates_m=coordinates,
        members=members,
        fixed_global_dofs=(0, 1, 2, 3, 4, 5),
        reference_external_loads=((9, 20.0), (10, -50.0)),
        rotation_coordinate_scale_m=4.0,
    )
    compilation = compile_corotational_fiber_frame_portal_profile(
        problem,
        model_content_hash=canonical_hash({"fixture": "public-portal.v1"}),
    )
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        (0.25, 0.5, 0.75, 1.0),
    )
    return create_corotational_fiber_frame_j1_j5_adapter(compilation, path)


def _result():
    return create_corotational_fiber_frame_engineering_result_ir(
        engineering_result_id="portal.engineering.v1",
        source_adapter=_adapter(),
    )


def test_exact_recovery_binds_all_engineering_axes_and_si_quantities() -> None:
    result = _result()
    manifest = result.to_manifest()
    descriptors = {row.name: row for row in result.descriptors}

    assert (result.node_count, result.member_count, result.section_count) == (4, 3, 9)
    assert result.fiber_count == 126
    assert (
        result.quantity_catalog_hash == default_result_quantity_catalog().catalog_hash
    )
    assert descriptors["reaction_force_n"].quantity_ids == ("reaction.force",)
    assert descriptors["fiber_stress_pa"].unit == "Pa"
    assert result.artifact("node_translation_m").shape == (4, 2)
    assert result.artifact("member_end_force_n").shape == (3, 4)
    assert result.artifact("section_axial_force_n").shape == (9,)
    assert result.artifact("fiber_stress_pa").shape == (126,)
    assert result.authority_axes["fallback"] == "not_used"
    assert result.authority_axes["public_api"] == "not_promoted"
    assert (
        validate_corotational_fiber_frame_engineering_result_manifest(manifest)
        == manifest
    )


def test_recovered_reactions_close_whole_portal_force_and_moment_equilibrium() -> None:
    result = _result()
    problem = result._adapter._compilation._problem
    forces = result.artifact("reaction_force_n")
    moments = result.artifact("reaction_moment_nm")
    translations = result.artifact("node_translation_m")
    external = problem.reference_external_load_vector() * 1000.0

    assert np.isclose(forces[:, 0].sum() + external[0::3].sum(), 0.0, atol=1.0e-4)
    assert np.isclose(forces[:, 1].sum() + external[1::3].sum(), 0.0, atol=1.0e-4)
    total_moment = float(moments.sum() + external[2::3].sum())
    for node, (initial_x_m, initial_y_m) in enumerate(problem.node_coordinates_m):
        x_m = initial_x_m + translations[node, 0]
        y_m = initial_y_m + translations[node, 1]
        total_moment += x_m * (forces[node, 1] + external[3 * node + 1])
        total_moment -= y_m * (forces[node, 0] + external[3 * node])
    assert abs(total_moment) <= 1.0e-3


def test_recovery_is_deterministic_and_artifacts_have_immutable_bytes_backing() -> None:
    first = _result()
    second = _result()

    assert first.engineering_result_hash == second.engineering_result_hash
    assert first.array_bundle_hash == second.array_bundle_hash
    for name in first._arrays:
        assert first.artifact(name).tobytes() == second.artifact(name).tobytes()
        assert first.artifact(name).flags.writeable is False
        with pytest.raises(ValueError):
            first.artifact(name).setflags(write=True)


def test_result_and_artifact_tampering_fail_closed() -> None:
    result = _result()
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="engineering_result_hash_mismatch",
    ):
        validate_corotational_fiber_frame_engineering_result_ir(
            replace(result, engineering_result_hash="sha256:" + "0" * 64)
        )

    arrays = dict(result._arrays)
    changed = np.array(arrays["fiber_stress_pa"], copy=True)
    changed[0] += 1.0
    arrays["fiber_stress_pa"] = immutable_array(changed, dtype="<f8")
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="array_mismatch",
    ):
        validate_corotational_fiber_frame_engineering_result_ir(
            replace(result, _arrays=MappingProxyType(arrays))
        )


def test_detached_manifest_cannot_promote_public_or_external_authority() -> None:
    manifest = _result().to_manifest()
    manifest["authority_axes"]["external_vv"] = "authoritative"

    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="engineering_result_hash_mismatch",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(manifest)
