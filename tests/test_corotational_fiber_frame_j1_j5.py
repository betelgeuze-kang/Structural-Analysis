from __future__ import annotations

from dataclasses import replace

import pytest

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_j1_j5 import (
    COROTATIONAL_FIBER_FRAME_PUBLIC_COMPILER_PROFILE,
    CorotationalFiberFrameJ1J5Error,
    compile_corotational_fiber_frame_portal_profile,
    create_corotational_fiber_frame_j1_j5_adapter,
    validate_corotational_fiber_frame_j1_j5_adapter,
    validate_corotational_fiber_frame_j1_j5_manifest,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    run_stateful_corotational_fiber_frame2d_load_path,
)
from structural_analysis.elements import StatefulCorotationalFiberBeam2D
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section


def _portal_problem(
    *, load_kn: float = 20.0
) -> StatefulCorotationalFiberFrame2DProblem:
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
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="public-corotational-portal",
        node_coordinates_m=coordinates,
        members=members,
        fixed_global_dofs=(0, 1, 2, 3, 4, 5),
        reference_external_loads=((9, load_kn), (10, -50.0)),
        rotation_coordinate_scale_m=4.0,
    )


def _adapter():
    problem = _portal_problem()
    model_hash = canonical_hash({"fixture": "public-corotational-portal.v1"})
    compilation = compile_corotational_fiber_frame_portal_profile(
        problem,
        model_content_hash=model_hash,
    )
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        (0.25, 0.5, 0.75, 1.0),
    )
    return create_corotational_fiber_frame_j1_j5_adapter(compilation, path)


def test_portal_compiler_and_j1_j5_adapter_replay_deterministically() -> None:
    first = _adapter()
    repeated = _adapter()
    manifest = first.to_manifest()

    assert first.adapter_hash == repeated.adapter_hash
    assert first.compiler_profile == COROTATIONAL_FIBER_FRAME_PUBLIC_COMPILER_PROFILE
    assert tuple(row.stage for row in first.stage_receipts) == (
        "J1",
        "J2",
        "J3",
        "J4",
        "J5",
    )
    assert all(all(row.checks.values()) for row in first.stage_receipts)
    assert manifest["terminal_load_factor"] == 1.0
    assert validate_corotational_fiber_frame_j1_j5_manifest(manifest) == manifest


def test_adapter_keeps_result_and_recovery_authority_uncreated() -> None:
    axes = _adapter().to_manifest()["authority_axes"]

    assert axes["convergence"] == "bounded_candidate"
    assert axes["numerical_result"] == "not_created"
    assert axes["reaction"] == "not_created"
    assert axes["member_force"] == "not_created"
    assert axes["section_resultant"] == "not_created"
    assert axes["fiber_result"] == "not_created"


def test_compiler_rejects_nonportal_topology() -> None:
    problem = _portal_problem()
    nonportal = replace(problem, members=problem.members[:2])

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_portal_topology_count_invalid",
    ):
        compile_corotational_fiber_frame_portal_profile(
            nonportal,
            model_content_hash=canonical_hash({"fixture": "invalid"}),
        )


def test_j5_rejects_non_full_load_path() -> None:
    problem = _portal_problem()
    compilation = compile_corotational_fiber_frame_portal_profile(
        problem,
        model_content_hash=canonical_hash({"fixture": "partial"}),
    )
    path = run_stateful_corotational_fiber_frame2d_load_path(problem, (0.25, 0.5))

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error, match="corotational_j5_gate_failed"
    ):
        create_corotational_fiber_frame_j1_j5_adapter(compilation, path)


def test_manifest_and_retained_adapter_tampering_fail_closed() -> None:
    adapter = _adapter()
    manifest = adapter.to_manifest()
    manifest["authority_axes"]["reaction"] = "authoritative"
    with pytest.raises(CorotationalFiberFrameJ1J5Error, match="adapter_hash_mismatch"):
        validate_corotational_fiber_frame_j1_j5_manifest(manifest)

    tampered = replace(adapter, terminal_load_factor=0.5)
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error, match="terminal_binding_invalid"
    ):
        validate_corotational_fiber_frame_j1_j5_adapter(tampered)
