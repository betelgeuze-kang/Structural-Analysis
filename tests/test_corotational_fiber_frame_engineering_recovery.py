from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

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
    CorotationalFiberFrameJ1J5Error,
    compile_corotational_fiber_frame_portal_profile,
    create_corotational_fiber_frame_j1_j5_adapter,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    run_stateful_corotational_fiber_frame2d_load_path,
)
from structural_analysis.elements import (
    AxialCurvatureSection,
    StatefulCorotationalFiberBeam2D,
)
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
                section=cast(AxialCurvatureSection, section),
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


def _rehash_manifest(manifest: dict) -> None:
    body = dict(manifest)
    body.pop("engineering_result_hash")
    manifest["engineering_result_hash"] = canonical_hash(body)


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
    assert result.authority_axes["member_features"] == "not_supported"
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


def test_recovery_preserves_source_bytes_and_rejects_source_tampering() -> None:
    adapter = _adapter()
    manifest_before = adapter.to_manifest()
    terminal_bytes_before = adapter._path.final_checkpoint.canonical_bytes()
    parent_bytes_before = adapter._path.steps[-1].parent_checkpoint.canonical_bytes()

    create_corotational_fiber_frame_engineering_result_ir(
        engineering_result_id="portal.source.immutable.v1",
        source_adapter=adapter,
    )

    assert adapter.to_manifest() == manifest_before
    assert adapter._path.final_checkpoint.canonical_bytes() == terminal_bytes_before
    assert (
        adapter._path.steps[-1].parent_checkpoint.canonical_bytes()
        == parent_bytes_before
    )

    with pytest.raises(
        CorotationalFiberFrameJ1J5Error,
        match="corotational_j1_j5_adapter_hash_mismatch",
    ):
        create_corotational_fiber_frame_engineering_result_ir(
            engineering_result_id="portal.source.tampered.v1",
            source_adapter=replace(adapter, adapter_hash="sha256:" + "0" * 64),
        )


def test_recovery_rejects_any_non_portal_source_adapter_type() -> None:
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_source_adapter_type_invalid",
    ):
        create_corotational_fiber_frame_engineering_result_ir(
            engineering_result_id="portal.wrong-source.v1",
            source_adapter=object(),  # type: ignore[arg-type]
        )


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


def test_live_result_contract_rejects_identity_metadata_and_array_set_drift() -> None:
    result = _result()

    with pytest.raises(KeyError, match="Unknown corotational engineering artifact"):
        result.artifact("not-an-artifact")
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_result_type_invalid",
    ):
        validate_corotational_fiber_frame_engineering_result_ir(cast(Any, {}))
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_result_id_invalid",
    ):
        create_corotational_fiber_frame_engineering_result_ir(
            engineering_result_id="not valid",
            source_adapter=result._adapter,
        )
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_result_binding_mismatch",
    ):
        validate_corotational_fiber_frame_engineering_result_ir(
            replace(result, member_count=result.member_count + 1)
        )

    arrays = dict(result._arrays)
    arrays.pop("fiber_area_m2")
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_result_array_set_invalid",
    ):
        validate_corotational_fiber_frame_engineering_result_ir(
            replace(result, _arrays=MappingProxyType(arrays))
        )


def test_detached_manifest_cannot_promote_public_or_external_authority() -> None:
    manifest = _result().to_manifest()
    manifest["authority_axes"]["external_vv"] = "authoritative"
    manifest["authority_axes"]["public_api"] = "promoted"
    _rehash_manifest(manifest)

    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_result_schema_invalid",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(manifest)


def test_detached_manifest_rejects_rehashed_descriptor_and_strict_type_drift() -> None:
    manifest = _result().to_manifest()
    manifest["array_descriptors"][0]["shape"] = [4, 3]
    manifest["array_bundle_hash"] = canonical_hash(manifest["array_descriptors"])
    _rehash_manifest(manifest)
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_descriptor_binding_mismatch",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(manifest)

    manifest = _result().to_manifest()
    manifest["counts"]["section"] = True
    _rehash_manifest(manifest)
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_result_schema_invalid",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(manifest)


def test_detached_manifest_rejects_hash_bundle_set_order_and_catalog_drift() -> None:
    valid = _result().to_manifest()

    nonfinite = deepcopy(valid)
    nonfinite["metrics"]["scatter_scaled_linf"] = float("nan")
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_result_manifest_invalid",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(nonfinite)

    aggregate = deepcopy(valid)
    aggregate["engineering_result_hash"] = "sha256:" + "0" * 64
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_result_hash_mismatch",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(aggregate)

    catalog = deepcopy(valid)
    catalog["quantity_catalog_hash"] = "sha256:" + "0" * 64
    _rehash_manifest(catalog)
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_result_binding_mismatch",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(catalog)

    bundle = deepcopy(valid)
    bundle["array_bundle_hash"] = "sha256:" + "0" * 64
    _rehash_manifest(bundle)
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_array_bundle_hash_mismatch",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(bundle)

    descriptor_set = deepcopy(valid)
    descriptor_set["array_descriptors"][0]["name"] = "renamed-artifact"
    descriptor_set["array_bundle_hash"] = canonical_hash(
        descriptor_set["array_descriptors"]
    )
    _rehash_manifest(descriptor_set)
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_descriptor_set_invalid",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(descriptor_set)

    order = deepcopy(valid)
    order["array_descriptors"][1]["order_hash"] = "sha256:" + "0" * 64
    order["array_bundle_hash"] = canonical_hash(order["array_descriptors"])
    _rehash_manifest(order)
    with pytest.raises(
        CorotationalFiberFrameEngineeringRecoveryError,
        match="corotational_engineering_order_hash_mismatch",
    ):
        validate_corotational_fiber_frame_engineering_result_manifest(order)


def test_focused_ci_lane_pins_engineering_recovery_branch_coverage() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/fiber-frame-execution-topology-ci.yml"
    ).read_text(encoding="utf-8")

    assert "Corotational portal engineering recovery branch coverage" in workflow
    assert "stateful_corotational_fiber_frame2d_engineering_recovery.py" in workflow
    assert "tests/test_corotational_fiber_frame_engineering_recovery.py" in workflow
    assert "coverage report --rcfile=/dev/null --fail-under=90" in workflow
