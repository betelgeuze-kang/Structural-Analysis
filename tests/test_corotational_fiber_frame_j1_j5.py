from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from dataclasses import replace
from typing import Any, cast

import pytest

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_j1_j5 import (
    COROTATIONAL_FIBER_FRAME_PUBLIC_COMPILER_PROFILE,
    CorotationalFiberFrameJ1J5Adapter,
    CorotationalFiberFrameJ1J5Error,
    compile_corotational_fiber_frame_portal_profile,
    create_corotational_fiber_frame_j1_j5_adapter,
    validate_corotational_fiber_frame_j1_j5_adapter,
    validate_corotational_fiber_frame_j1_j5_manifest,
    validate_corotational_portal_compilation,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    run_stateful_corotational_fiber_frame2d_load_path,
)
from structural_analysis.elements import (
    AxialCurvatureSection,
    StatefulCorotationalFiberBeam2D,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials import make_rectangular_stateful_rc_fiber_section


def _portal_problem(
    *,
    load_kn: float = 20.0,
    edges: tuple[tuple[str, int, int], ...] = (
        ("column-left", 0, 2),
        ("column-right", 1, 3),
        ("beam-top", 2, 3),
    ),
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
                section=cast(AxialCurvatureSection, section),
                integration_order=3,
                element_id=member_id,
            ),
        )
        for member_id, node_i, node_j in edges
    )
    return StatefulCorotationalFiberFrame2DProblem(
        case_id="public-corotational-portal",
        node_coordinates_m=coordinates,
        members=members,
        fixed_global_dofs=(0, 1, 2, 3, 4, 5),
        reference_external_loads=((9, load_kn), (10, -50.0)),
        rotation_coordinate_scale_m=4.0,
    )


def _build_adapter() -> CorotationalFiberFrameJ1J5Adapter:
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


@pytest.fixture(scope="module")
def adapter() -> CorotationalFiberFrameJ1J5Adapter:
    return _build_adapter()


def _rehash_adapter(manifest: dict[str, Any]) -> None:
    body = deepcopy(manifest)
    body.pop("adapter_hash")
    manifest["adapter_hash"] = canonical_hash(body)


def _rehash_compilation(manifest: dict[str, Any]) -> None:
    compilation = deepcopy(manifest["compilation"])
    compilation.pop("compiler_hash")
    manifest["compilation"]["compiler_hash"] = canonical_hash(compilation)
    manifest["compiler_hash"] = manifest["compilation"]["compiler_hash"]


def _rehash_stage(manifest: dict[str, Any], index: int) -> None:
    row = deepcopy(manifest["stage_receipts"][index])
    row.pop("stage_hash")
    manifest["stage_receipts"][index]["stage_hash"] = canonical_hash(row)


def test_portal_compiler_and_j1_j5_adapter_replay_deterministically() -> None:
    first = _build_adapter()
    repeated = _build_adapter()
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
    assert manifest["compilation"]["node_count"] == 4
    assert manifest["compilation"]["member_count"] == 3
    assert validate_corotational_fiber_frame_j1_j5_manifest(manifest) == manifest

    compilation_body = deepcopy(manifest["compilation"])
    compiler_hash = compilation_body.pop("compiler_hash")
    assert compiler_hash == canonical_hash(compilation_body)
    for row in manifest["stage_receipts"]:
        stage_body = deepcopy(row)
        stage_hash = stage_body.pop("stage_hash")
        assert stage_hash == canonical_hash(stage_body)


def test_adapter_keeps_unsupported_and_result_authority_uncreated(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    manifest = adapter.to_manifest()
    axes = manifest["authority_axes"]

    assert axes["convergence"] == "bounded_candidate"
    assert axes["member_features"] == "not_supported"
    assert axes["numerical_result"] == "not_created"
    assert axes["reaction"] == "not_created"
    assert axes["member_force"] == "not_created"
    assert axes["section_resultant"] == "not_created"
    assert axes["fiber_result"] == "not_created"
    assert (
        "standalone_manifest_source_authenticity_not_established"
        in manifest["limitations"]
    )


def test_stage_receipt_body_is_deeply_immutable(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    body = adapter.stage_receipts[0].body

    with pytest.raises(TypeError):
        cast(Any, body)["changed"] = True
    with pytest.raises(TypeError):
        cast(Any, body["member_contract_hashes"])[0] = "changed"


@pytest.mark.parametrize(
    ("problem", "error_code"),
    [
        (
            replace(_portal_problem(), members=_portal_problem().members[:2]),
            "corotational_portal_topology_count_invalid",
        ),
        (
            replace(_portal_problem(), fixed_global_dofs=(0, 1, 2)),
            "corotational_portal_support_invalid",
        ),
        (
            replace(_portal_problem(), reference_external_loads=((0, 20.0),)),
            "corotational_portal_load_location_invalid",
        ),
        (
            replace(
                _portal_problem(),
                prescribed_displacements=((0, 1.0e-4),),
            ),
            "corotational_portal_prescribed_displacement_unsupported",
        ),
        (
            _portal_problem(
                edges=(
                    ("column-left", 0, 2),
                    ("diagonal", 1, 2),
                    ("beam-top", 2, 3),
                )
            ),
            "corotational_portal_connectivity_invalid",
        ),
    ],
)
def test_compiler_rejects_out_of_profile_problem(
    problem: StatefulCorotationalFiberFrame2DProblem,
    error_code: str,
) -> None:
    with pytest.raises(CorotationalFiberFrameJ1J5Error, match=error_code):
        compile_corotational_fiber_frame_portal_profile(
            problem,
            model_content_hash=canonical_hash({"fixture": error_code}),
        )


def test_compiler_rejects_invalid_type_and_model_hash() -> None:
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_portal_problem_type_invalid",
    ):
        compile_corotational_fiber_frame_portal_profile(
            cast(Any, {}),
            model_content_hash=canonical_hash({"fixture": "invalid-type"}),
        )

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error, match="corotational_hash_invalid"
    ):
        compile_corotational_fiber_frame_portal_profile(
            _portal_problem(),
            model_content_hash="not-a-hash",
        )


def test_compilation_retained_source_and_hash_tampering_fail_closed(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    compilation = adapter._compilation
    validate_corotational_portal_compilation(compilation)

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_portal_compiler_hash_mismatch",
    ):
        validate_corotational_portal_compilation(
            replace(
                compilation,
                model_content_hash=canonical_hash({"fixture": "changed"}),
            )
        )


def test_typed_compilation_validation_rejects_type_profile_source_and_binding(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    compilation = adapter._compilation

    cases = (
        (
            cast(Any, {}),
            "corotational_portal_compilation_type_invalid",
        ),
        (
            replace(compilation, compiler_profile="other"),
            "corotational_portal_compiler_profile_invalid",
        ),
        (
            replace(
                compilation,
                _problem=replace(compilation._problem, case_id="changed-source"),
            ),
            "corotational_portal_problem_hash_mismatch",
        ),
        (
            replace(compilation, node_count=5),
            "corotational_portal_compilation_binding_invalid",
        ),
    )
    for candidate, error_code in cases:
        with pytest.raises(CorotationalFiberFrameJ1J5Error, match=error_code):
            validate_corotational_portal_compilation(candidate)


def test_typed_adapter_validation_rejects_type_axes_hash_and_path(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_adapter_type_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_adapter(cast(Any, {}))

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_adapter_binding_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_adapter(
            replace(adapter, authority_axes=cast(Any, object()))
        )

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_adapter_hash_mismatch",
    ):
        validate_corotational_fiber_frame_j1_j5_adapter(
            replace(adapter, adapter_hash=canonical_hash({"fixture": "changed"}))
        )

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_path_type_invalid",
    ):
        create_corotational_fiber_frame_j1_j5_adapter(
            adapter._compilation,
            cast(Any, {}),
        )


def test_j3_rejects_non_monotonic_load_ancestry() -> None:
    problem = _portal_problem()
    compilation = compile_corotational_fiber_frame_portal_profile(
        problem,
        model_content_hash=canonical_hash({"fixture": "non-monotonic"}),
    )
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        (0.5, 0.25, 1.0),
    )
    assert path.contract_pass is True

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error, match="corotational_j3_gate_failed"
    ):
        create_corotational_fiber_frame_j1_j5_adapter(compilation, path)


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


def test_retained_adapter_tampering_fails_replay(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j5_terminal_binding_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_adapter(
            replace(adapter, terminal_load_factor=0.5)
        )

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_adapter_binding_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_adapter(
            replace(adapter, authority_axes={"reaction": "authoritative"})
        )

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_replay_mismatch",
    ):
        validate_corotational_fiber_frame_j1_j5_adapter(
            replace(adapter, stage_receipts=adapter.stage_receipts[::-1])
        )


def test_manifest_hash_tampering_fails_closed(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    manifest = adapter.to_manifest()
    manifest["stage_receipts"][0]["body"]["free_global_dofs"][0] = 99

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_stage_hash_mismatch",
    ):
        validate_corotational_fiber_frame_j1_j5_manifest(manifest)


def test_rehashed_manifest_cannot_change_fixed_claim_semantics(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    authority = adapter.to_manifest()
    authority["authority_axes"]["reaction"] = "authoritative"
    _rehash_adapter(authority)
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_schema_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_manifest(authority)

    stage = adapter.to_manifest()
    stage["stage_receipts"][0]["contract_profile"] = "other"
    _rehash_stage(stage, 0)
    _rehash_adapter(stage)
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_schema_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_manifest(stage)


def test_rehashed_compilation_must_remain_bound_and_partition_nodes(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    rebound = adapter.to_manifest()
    rebound["compilation"]["case_id"] = "other-case"
    _rehash_compilation(rebound)
    _rehash_adapter(rebound)
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_compilation_binding_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_manifest(rebound)

    overlapping = adapter.to_manifest()
    overlapping["compilation"]["top_node_indices"] = [1, 2]
    _rehash_compilation(overlapping)
    _rehash_adapter(overlapping)
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_compilation_binding_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_manifest(overlapping)


def test_manifest_non_json_values_use_stable_fail_closed_error(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    manifest = adapter.to_manifest()
    manifest["extra"] = object()

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_manifest_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_manifest(manifest)


def test_manifest_rejects_each_hash_binding_layer(
    adapter: CorotationalFiberFrameJ1J5Adapter,
) -> None:
    compiler_content = adapter.to_manifest()
    compiler_content["compilation"]["case_id"] = "changed"
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_portal_compiler_hash_mismatch",
    ):
        validate_corotational_fiber_frame_j1_j5_manifest(compiler_content)

    compiler_binding = adapter.to_manifest()
    compiler_binding["compiler_hash"] = canonical_hash({"fixture": "other-compiler"})
    _rehash_adapter(compiler_binding)
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_compilation_binding_invalid",
    ):
        validate_corotational_fiber_frame_j1_j5_manifest(compiler_binding)

    aggregate = adapter.to_manifest()
    aggregate["case_id"] = "changed"
    aggregate["compilation"]["case_id"] = "changed"
    _rehash_compilation(aggregate)
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_adapter_hash_mismatch",
    ):
        validate_corotational_fiber_frame_j1_j5_manifest(aggregate)


def test_portal_compiler_rejects_non_string_hash() -> None:
    with pytest.raises(
        CorotationalFiberFrameJ1J5Error, match="corotational_hash_invalid"
    ):
        compile_corotational_fiber_frame_portal_profile(
            _portal_problem(),
            model_content_hash=cast(Any, None),
        )


def test_focused_ci_lane_pins_j1_j5_branch_coverage() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (
        root / ".github" / "workflows" / "fiber-frame-execution-topology-ci.yml"
    ).read_text(encoding="utf-8")

    assert "Corotational portal J1-J5 branch coverage" in workflow
    assert (
        '--include="src/structural_analysis/assembly/stateful_corotational_fiber_frame2d_j1_j5.py"'
        in workflow
    )
    assert "coverage report --rcfile=/dev/null --fail-under=90" in workflow
