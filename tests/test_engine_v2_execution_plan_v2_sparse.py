from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import MappingProxyType

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.backends.cpu_reference.linear_static import (  # noqa: E402
    assemble_linear_static_operator,
    solve_linear_static,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    _artifact_hash,
    _descriptor,
    _numeric_buffer_hash,
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    ExecutionPlanV2Error,
    _array_descriptor,
    _compile_symbolic_pattern,
    _numeric_snapshot_hash,
    _operator_hash,
    _partition_hash,
    _plan_hash,
    _symbolic_reuse_hash,
    compile_execution_plan_v2,
    validate_execution_plan_v2,
)
from structural_analysis.engine_v2.operators.sparse_linear_static import (  # noqa: E402
    SparseLinearStaticErrorV2,
    _result_array_descriptor,
    _result_hash,
    solve_sparse_execution_plan_v2,
    sparse_reduced_jvp,
    validate_sparse_linear_static_result_v2,
)
from structural_analysis.model_ir import parse_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
PLAN_SCHEMA = (
    REPO_ROOT / "src/structural_analysis/schemas/execution_plan_v2.schema.json"
)
RESULT_SCHEMA = (
    REPO_ROOT
    / "src/structural_analysis/schemas/sparse_linear_static_result_v2.schema.json"
)


def _payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _buffers(payload: dict | None = None, load_pattern_id: str = "LC_AXIAL"):
    return pack_solver_model_buffers(
        parse_model_ir_v2(_payload() if payload is None else payload),
        load_pattern_id=load_pattern_id,
    )


def _truss_payload() -> dict:
    payload = _payload()
    payload["sections"][0]["family_id"] = "truss_3d"
    payload["sections"][0]["parameters"] = {"area_m2": 0.02}
    element = payload["elements"][0]
    element["type"] = "truss_3d"
    element["formulation"] = "linear_truss_3d"
    element.pop("local_axis_rotation_rad")
    element.pop("releases")
    payload["constraints"].append(
        {
            "id": "BC2",
            "index": 1,
            "type": "fixed_dofs",
            "node_id": "N2",
            "dofs": ["UY", "UZ", "RX", "RY", "RZ"],
            "prescribed_values_si": {},
            "source_id": "generated:BC2",
            "extensions": {},
        }
    )
    return payload


def _two_element_payload() -> dict:
    payload = _payload()
    payload["nodes"].append(
        {
            "id": "N3",
            "index": 2,
            "coordinates_m": [4.0, 0.0, 0.0],
            "source_id": "generated:N3",
            "extensions": {},
        }
    )
    second = deepcopy(payload["elements"][0])
    second.update(
        {
            "id": "E2",
            "index": 1,
            "node_ids": ["N2", "N3"],
            "source_id": "generated:E2",
        }
    )
    payload["elements"].append(second)
    for pattern in payload["load_patterns"]:
        pattern["nodal_loads"][0]["node_id"] = "N3"
    return payload


def _chain_payload(node_count: int) -> dict:
    payload = _payload()
    node_template = deepcopy(payload["nodes"][0])
    element_template = deepcopy(payload["elements"][0])
    payload["nodes"] = []
    for index in range(node_count):
        node = deepcopy(node_template)
        node.update(
            {
                "id": f"N{index + 1}",
                "index": index,
                "coordinates_m": [2.0 * index, 0.0, 0.0],
                "source_id": f"generated:N{index + 1}",
            }
        )
        payload["nodes"].append(node)
    payload["elements"] = []
    for index in range(node_count - 1):
        element = deepcopy(element_template)
        element.update(
            {
                "id": f"E{index + 1}",
                "index": index,
                "node_ids": [f"N{index + 1}", f"N{index + 2}"],
                "source_id": f"generated:E{index + 1}",
            }
        )
        payload["elements"].append(element)
    for pattern in payload["load_patterns"]:
        pattern["nodal_loads"][0]["node_id"] = f"N{node_count}"
    return payload


def _fully_rehash_result(plan, result, **array_updates):
    arrays = {
        name: result.array(name)
        for name in (
            "displacements_si",
            "reactions_si",
            "residual_si",
            "element_end_forces_local_si",
            "element_strain_energy_j",
        )
    }
    arrays.update(array_updates)
    descriptors = tuple(
        _result_array_descriptor(row.name, arrays[row.name])
        for row in result.descriptors
    )
    forged = replace(result, descriptors=descriptors, **array_updates)
    return replace(
        forged,
        result_hash=_result_hash(
            plan=plan,
            status=forged.status,
            descriptors=descriptors,
            total_energy=forged.total_strain_energy_j,
            free_residual_linf=forged.free_residual_linf,
            scaled_free_residual=forged.scaled_free_residual,
        ),
    )


def _plan_arrays(plan) -> dict[str, np.ndarray]:
    return {row.name: plan.array(row.name) for row in plan.descriptors}


def _plan_array_tuple(plan, arrays: dict[str, np.ndarray]) -> tuple[np.ndarray, ...]:
    return tuple(arrays[row.name] for row in plan.descriptors)


def test_v2_plan_and_result_schemas_are_draft202012_and_strict() -> None:
    plan_schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
    result_schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(plan_schema)
    Draft202012Validator.check_schema(result_schema)
    plan_validator = Draft202012Validator(plan_schema)
    result_validator = Draft202012Validator(result_schema)

    plan = compile_execution_plan_v2(_buffers())
    result = solve_sparse_execution_plan_v2(plan)
    assert not list(plan_validator.iter_errors(plan.to_dict()))
    assert not list(result_validator.iter_errors(result.to_dict()))

    forged_plan = plan.to_dict()
    forged_plan["numeric_snapshot"]["dense_pointer"] = "0x1234"
    assert list(plan_validator.iter_errors(forged_plan))
    forged_result = result.to_dict()
    forged_result["claim_boundary"]["fallback_used"] = True
    assert list(result_validator.iter_errors(forged_result))


def test_sparse_v2_public_api_exports_canonical_types_and_entrypoints() -> None:
    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.contracts as contracts
    import structural_analysis.engine_v2.operators as operators

    assert engine_v2.ExecutionPlanV2 is contracts.ExecutionPlanV2
    assert engine_v2.compile_execution_plan_v2 is contracts.compile_execution_plan_v2
    assert engine_v2.SparseLinearStaticResultV2 is operators.SparseLinearStaticResultV2
    assert (
        engine_v2.solve_sparse_execution_plan_v2
        is operators.solve_sparse_execution_plan_v2
    )
    assert engine_v2.sparse_reduced_jvp is operators.sparse_reduced_jvp


def test_v2_artifact_is_sparse_only_deterministic_and_retains_zero_slots() -> None:
    first = compile_execution_plan_v2(_buffers())
    second = compile_execution_plan_v2(_buffers())

    assert first.to_dict() == second.to_dict()
    assert first.plan_hash == second.plan_hash
    assert first.numeric_snapshot_hash == second.numeric_snapshot_hash
    assert "global_stiffness_dense" not in {row.name for row in first.descriptors}
    assert all(
        array.shape != (first.dof_count, first.dof_count) for array in first._arrays
    )
    assert np.count_nonzero(first.array("global_stiffness_csr_values") == 0.0) > 0
    assert first.to_dict()["symbolic_plan"]["structural_zero_slots_retained"] is True
    assert (
        first.to_dict()["claim_boundary"]["global_dense_matrix_materialized"] is False
    )
    for descriptor in first.descriptors:
        array = first.array(descriptor.name)
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)
    for name in (
        "global_stiffness_csr_values",
        "reduced_stiffness_csr_values",
        "global_load",
        "recovery_transform_global_to_local",
        "recovery_stiffness_local",
    ):
        values = first.array(name)
        assert not np.any(np.signbit(values[values == 0.0]))


def test_symbolic_reuse_hash_is_separate_from_numeric_and_exact_binding() -> None:
    axial = compile_execution_plan_v2(_buffers(load_pattern_id="LC_AXIAL"))
    weak = compile_execution_plan_v2(_buffers(load_pattern_id="LC_WEAK"))
    rotated_payload = _payload()
    rotated_payload["nodes"][1]["coordinates_m"] = [1.0, 2.0, 3.0]
    rotated_payload["elements"][0]["local_axis_rotation_rad"] = 0.37
    rotated = compile_execution_plan_v2(_buffers(rotated_payload, "LC_AXIAL"))

    assert axial.symbolic_reuse_hash == weak.symbolic_reuse_hash
    assert axial.symbolic_reuse_hash == rotated.symbolic_reuse_hash
    assert axial.numeric_snapshot_hash != weak.numeric_snapshot_hash
    assert axial.numeric_snapshot_hash != rotated.numeric_snapshot_hash
    assert axial.plan_hash != weak.plan_hash != rotated.plan_hash


def test_validator_reaccumulates_csr_and_rejects_fully_rehashed_value_tamper() -> None:
    plan = compile_execution_plan_v2(_buffers())
    arrays = _plan_arrays(plan)
    forged_values = np.asarray(arrays["global_stiffness_csr_values"]).copy()
    forged_values[0] += 1.0
    arrays["global_stiffness_csr_values"] = immutable_array(forged_values, dtype="<f8")
    descriptors = tuple(
        _array_descriptor(row.name, arrays[row.name])
        if row.name == "global_stiffness_csr_values"
        else row
        for row in plan.descriptors
    )
    descriptor_map = {row.name: row for row in descriptors}
    numeric_hash = _numeric_snapshot_hash(
        descriptor_map,
        recovery_operator_hash=plan.recovery_operator_hash,
        solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
    )
    forged = replace(
        plan,
        descriptors=descriptors,
        _arrays=_plan_array_tuple(plan, arrays),
        numeric_snapshot_hash=numeric_hash,
        operator_hash=_operator_hash(
            numeric_snapshot_hash=numeric_hash,
            partition_hash=plan.partition_hash,
            symbolic_reuse_hash=plan.symbolic_reuse_hash,
        ),
        plan_hash="sha256:" + "0" * 64,
    )
    forged = replace(forged, plan_hash=_plan_hash(forged))

    with pytest.raises(ExecutionPlanV2Error) as error:
        validate_execution_plan_v2(forged)
    assert error.value.code == "execution_plan_v2_reassembly_mismatch"


def test_validator_rejects_rehashed_local_operator_tamper_against_source() -> None:
    plan = compile_execution_plan_v2(_buffers())
    arrays = _plan_arrays(plan)
    local = np.asarray(arrays["recovery_stiffness_local"]).copy()
    local[0, 0, 0] += 1.0
    arrays["recovery_stiffness_local"] = immutable_array(local, dtype="<f8")
    descriptors = tuple(
        _array_descriptor(row.name, arrays[row.name])
        if row.name == "recovery_stiffness_local"
        else row
        for row in plan.descriptors
    )
    forged = replace(
        plan, descriptors=descriptors, _arrays=_plan_array_tuple(plan, arrays)
    )

    with pytest.raises(ExecutionPlanV2Error) as error:
        validate_execution_plan_v2(forged)
    assert error.value.code == "execution_plan_v2_source_numeric_mismatch"


def test_validator_rejects_fully_rehashed_partition_forgery_against_support_mask() -> (
    None
):
    plan = compile_execution_plan_v2(_buffers())
    arrays = _plan_arrays(plan)
    constrained = np.asarray([0, 1, 2, 3, 4, 6], dtype="<i4")
    free = np.asarray([5, 7, 8, 9, 10, 11], dtype="<i4")
    global_to_free = np.full(plan.dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    symbolic = _compile_symbolic_pattern(
        dof_count=plan.dof_count,
        element_global_dofs=plan.array("element_global_dofs"),
        free_dofs=free,
        global_to_free=global_to_free,
    )
    arrays.update(
        {
            "constrained_dofs": immutable_array(constrained, dtype="<i4"),
            "free_dofs": immutable_array(free, dtype="<i4"),
            "global_to_free": immutable_array(global_to_free, dtype="<i4"),
            **symbolic,
        }
    )
    arrays["reduced_stiffness_csr_values"] = immutable_array(
        arrays["global_stiffness_csr_values"][
            arrays["reduced_csr_global_value_indices"]
        ],
        dtype="<f8",
    )
    descriptors = tuple(
        _array_descriptor(row.name, arrays[row.name]) for row in plan.descriptors
    )
    descriptor_map = {row.name: row for row in descriptors}
    partition_hash = _partition_hash(descriptor_map)
    symbolic_hash = _symbolic_reuse_hash(
        descriptor_map,
        dof_count=plan.dof_count,
        free_count=free.size,
    )
    numeric_hash = _numeric_snapshot_hash(
        descriptor_map,
        recovery_operator_hash=plan.recovery_operator_hash,
        solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
    )
    forged = replace(
        plan,
        partition_hash=partition_hash,
        symbolic_reuse_hash=symbolic_hash,
        numeric_snapshot_hash=numeric_hash,
        operator_hash=_operator_hash(
            numeric_snapshot_hash=numeric_hash,
            partition_hash=partition_hash,
            symbolic_reuse_hash=symbolic_hash,
        ),
        descriptors=descriptors,
        _arrays=_plan_array_tuple(plan, arrays),
        plan_hash="sha256:" + "0" * 64,
    )
    forged = replace(forged, plan_hash=_plan_hash(forged))

    with pytest.raises(ExecutionPlanV2Error) as error:
        validate_execution_plan_v2(forged, expected_buffers=_buffers())
    assert error.value.code == "execution_plan_v2_source_partition_mismatch"


def test_plan_rejects_mutable_array_and_descriptor_containers() -> None:
    plan = compile_execution_plan_v2(_buffers())

    with pytest.raises(ExecutionPlanV2Error) as array_error:
        validate_execution_plan_v2(
            replace(plan, _arrays=MappingProxyType(_plan_arrays(plan)))
        )
    assert array_error.value.code == "execution_plan_v2_container_invalid"

    with pytest.raises(ExecutionPlanV2Error) as descriptor_error:
        validate_execution_plan_v2(replace(plan, descriptors=list(plan.descriptors)))
    assert descriptor_error.value.code == "execution_plan_v2_container_invalid"

    class ScalarOverride(np.ndarray):
        pass

    arrays = list(plan._arrays)
    values_index = next(
        index
        for index, row in enumerate(plan.descriptors)
        if row.name == "global_stiffness_csr_values"
    )
    arrays[values_index] = arrays[values_index].view(ScalarOverride)
    with pytest.raises(ExecutionPlanV2Error) as subclass_error:
        validate_execution_plan_v2(replace(plan, _arrays=tuple(arrays)))
    assert subclass_error.value.code == "execution_plan_v2_container_invalid"


def test_plan_tuple_snapshot_is_not_affected_by_external_mapping_pointer_swap() -> None:
    plan = compile_execution_plan_v2(_buffers())
    external = _plan_arrays(plan)
    snapshot = tuple(external[row.name] for row in plan.descriptors)
    detached = replace(plan, _arrays=snapshot)
    validate_execution_plan_v2(detached)
    before = detached.residual(np.zeros(detached.dof_count))
    external["global_load"] = immutable_array(np.zeros(detached.dof_count), dtype="<f8")

    np.testing.assert_array_equal(
        detached.residual(np.zeros(detached.dof_count)), before
    )


def test_owned_readonly_and_ndarray_subclass_sources_fail_preflight() -> None:
    buffers = _buffers()
    arrays = dict(buffers._arrays)
    owned = np.array(arrays["node_coordinates_m"], copy=True)
    owned.setflags(write=False)
    arrays["node_coordinates_m"] = owned
    owned_forgery = replace(buffers, _arrays=MappingProxyType(arrays))

    with pytest.raises(ExecutionPlanV2Error) as owned_error:
        compile_execution_plan_v2(owned_forgery)
    assert owned_error.value.code == "execution_plan_v2_source_buffer_invalid"

    class ScalarOverride(np.ndarray):
        pass

    subclass_arrays = dict(buffers._arrays)
    subclass_arrays["material_properties_si"] = subclass_arrays[
        "material_properties_si"
    ].view(ScalarOverride)
    subclass_forgery = replace(buffers, _arrays=MappingProxyType(subclass_arrays))
    with pytest.raises(ExecutionPlanV2Error) as subclass_error:
        compile_execution_plan_v2(subclass_forgery)
    assert subclass_error.value.code == "execution_plan_v2_source_buffer_invalid"

    class EqualDescriptorProxy:
        def __init__(self, target):
            self.__dict__.update(target.__dict__)

        def __eq__(self, other):
            return True

        def to_dict(self):
            return dict(self.__dict__)

    descriptor_rows = list(buffers.descriptors)
    descriptor_rows[0] = EqualDescriptorProxy(descriptor_rows[0])
    descriptor_forgery = replace(buffers, descriptors=tuple(descriptor_rows))
    with pytest.raises(ExecutionPlanV2Error) as descriptor_error:
        compile_execution_plan_v2(descriptor_forgery)
    assert descriptor_error.value.code == "execution_plan_v2_source_buffer_invalid"


def test_result_rejects_mutable_descriptor_container() -> None:
    plan = compile_execution_plan_v2(_buffers())
    result = solve_sparse_execution_plan_v2(plan)

    with pytest.raises(SparseLinearStaticErrorV2) as error:
        validate_sparse_linear_static_result_v2(
            replace(result, descriptors=list(result.descriptors)),
            expected_plan=plan,
        )
    assert error.value.code == "sparse_linear_static_result_container_invalid"

    class ScalarOverride(np.ndarray):
        pass

    with pytest.raises(SparseLinearStaticErrorV2) as subclass_error:
        validate_sparse_linear_static_result_v2(
            replace(
                result,
                displacements_si=result.displacements_si.view(ScalarOverride),
            ),
            expected_plan=plan,
        )
    assert subclass_error.value.code == "sparse_linear_static_result_array_invalid"


def test_result_rejects_fully_rehashed_reaction_byte_tamper() -> None:
    plan = compile_execution_plan_v2(_buffers())
    result = solve_sparse_execution_plan_v2(plan)
    reactions = np.asarray(result.reactions_si).copy()
    reactions.reshape(-1)[plan.constrained_dofs[0]] += 1.0e-8
    forged = _fully_rehash_result(
        plan,
        result,
        reactions_si=immutable_array(reactions, dtype="<f8"),
    )

    with pytest.raises(SparseLinearStaticErrorV2) as error:
        validate_sparse_linear_static_result_v2(forged, expected_plan=plan)
    assert error.value.code == "sparse_linear_static_result_reaction_mismatch"


def test_result_enforces_exact_zero_free_reaction_slots() -> None:
    plan = compile_execution_plan_v2(_buffers())
    result = solve_sparse_execution_plan_v2(plan)
    reactions = np.asarray(result.reactions_si).copy()
    reactions.reshape(-1)[plan.free_dofs[0]] = np.nextafter(0.0, 1.0)
    forged = _fully_rehash_result(
        plan,
        result,
        reactions_si=immutable_array(reactions, dtype="<f8"),
    )

    with pytest.raises(SparseLinearStaticErrorV2) as error:
        validate_sparse_linear_static_result_v2(forged, expected_plan=plan)
    assert error.value.code == "sparse_linear_static_result_free_reaction_nonzero"


def test_result_rejects_fully_rehashed_negative_element_energy() -> None:
    payload = _payload()
    axial = next(row for row in payload["load_patterns"] if row["id"] == "LC_AXIAL")
    axial["nodal_loads"][0]["node_id"] = "N1"
    plan = compile_execution_plan_v2(_buffers(payload))
    result = solve_sparse_execution_plan_v2(plan)
    energy = np.asarray(result.element_strain_energy_j).copy()
    energy[0] = -5.0e-13
    forged = _fully_rehash_result(
        plan,
        result,
        element_strain_energy_j=immutable_array(energy, dtype="<f8"),
    )

    with pytest.raises(SparseLinearStaticErrorV2) as error:
        validate_sparse_linear_static_result_v2(forged, expected_plan=plan)
    assert error.value.code == "sparse_linear_static_result_negative_energy"


def test_singular_sparse_direct_solve_has_stable_fail_closed_error() -> None:
    payload = _truss_payload()
    payload["constraints"] = [payload["constraints"][0]]
    plan = compile_execution_plan_v2(_buffers(payload))

    with pytest.raises(SparseLinearStaticErrorV2) as error:
        solve_sparse_execution_plan_v2(plan)
    assert error.value.code == "sparse_linear_static_singular_or_failed_solve"


def test_result_validator_rejects_physics_consistent_singular_ready_forgery() -> None:
    stable_payload = _truss_payload()
    axial = next(
        row for row in stable_payload["load_patterns"] if row["id"] == "LC_AXIAL"
    )
    axial["nodal_loads"][0]["node_id"] = "N1"
    stable_plan = compile_execution_plan_v2(_buffers(stable_payload))
    stable_result = solve_sparse_execution_plan_v2(stable_plan)
    singular_payload = deepcopy(stable_payload)
    singular_payload["constraints"] = [singular_payload["constraints"][0]]
    singular_plan = compile_execution_plan_v2(_buffers(singular_payload))
    forged = replace(
        stable_result,
        execution_plan_hash=singular_plan.plan_hash,
        operator_version=singular_plan.operator_version,
        operator_hash=singular_plan.operator_hash,
        numeric_snapshot_hash=singular_plan.numeric_snapshot_hash,
        constrained_dofs=singular_plan.constrained_dofs,
        free_dofs=singular_plan.free_dofs,
    )
    forged = replace(
        forged,
        result_hash=_result_hash(
            plan=singular_plan,
            status=forged.status,
            descriptors=forged.descriptors,
            total_energy=forged.total_strain_energy_j,
            free_residual_linf=forged.free_residual_linf,
            scaled_free_residual=forged.scaled_free_residual,
        ),
    )

    with pytest.raises(SparseLinearStaticErrorV2) as error:
        validate_sparse_linear_static_result_v2(forged, expected_plan=singular_plan)
    assert error.value.code == "sparse_linear_static_singular_or_failed_solve"


def test_nonzero_prescribed_displacement_fails_closed() -> None:
    buffers = _buffers()
    arrays = dict(buffers._arrays)
    prescribed = np.asarray(arrays["prescribed_values_si"]).copy()
    prescribed[0, 0] = 1.0e-3
    arrays["prescribed_values_si"] = immutable_array(prescribed, dtype="<f8")
    descriptors = tuple(
        _descriptor(row.name, arrays[row.name])
        if row.name == "prescribed_values_si"
        else row
        for row in buffers.descriptors
    )
    numeric_hash = _numeric_buffer_hash(descriptors, buffers.code_tables)
    buffers = replace(
        buffers,
        descriptors=descriptors,
        numeric_buffer_hash=numeric_hash,
        artifact_hash=_artifact_hash(
            model_ir_content_hash=buffers.model_ir_content_hash,
            load_pattern_id=buffers.load_pattern_id,
            numeric_buffer_hash=numeric_hash,
            entity_mapping_hash=buffers.entity_mapping_hash,
        ),
        _arrays=MappingProxyType(arrays),
    )

    with pytest.raises(ExecutionPlanV2Error) as error:
        compile_execution_plan_v2(buffers)
    assert error.value.code == "execution_plan_v2_nonzero_prescribed_unsupported"


@pytest.mark.parametrize(
    "load_pattern_id", ["LC_AXIAL", "LC_WEAK", "LC_STRONG", "LC_TORSION"]
)
def test_sparse_v2_matches_v1_cantilever_results(load_pattern_id: str) -> None:
    buffers = _buffers(load_pattern_id=load_pattern_id)
    reference = solve_linear_static(buffers, matrix_backend="dense")
    result = solve_sparse_execution_plan_v2(compile_execution_plan_v2(buffers))

    assert result.status == "ready"
    np.testing.assert_allclose(
        result.displacements_si, reference.displacements_si, rtol=1e-12, atol=1e-12
    )
    np.testing.assert_allclose(
        result.reactions_si, reference.reactions_si, rtol=1e-12, atol=1e-8
    )
    np.testing.assert_allclose(
        result.residual_si, reference.residual_si, rtol=1e-12, atol=1e-8
    )
    np.testing.assert_allclose(
        result.element_end_forces_local_si,
        reference.element_end_forces_local_si,
        rtol=1e-12,
        atol=1e-8,
    )
    np.testing.assert_allclose(
        result.element_strain_energy_j,
        reference.element_strain_energy_j,
        rtol=1e-12,
        atol=1e-12,
    )
    assert result.total_strain_energy_j == pytest.approx(
        reference.total_strain_energy_j, rel=1e-12, abs=1e-12
    )


@pytest.mark.parametrize(
    ("payload", "load_pattern_id"),
    [
        (_truss_payload(), "LC_AXIAL"),
        (_two_element_payload(), "LC_AXIAL"),
    ],
)
def test_sparse_v2_matches_v1_truss_and_multi_element(
    payload: dict, load_pattern_id: str
) -> None:
    buffers = _buffers(payload, load_pattern_id)
    reference = solve_linear_static(buffers, matrix_backend="dense")
    result = solve_sparse_execution_plan_v2(compile_execution_plan_v2(buffers))

    np.testing.assert_allclose(
        result.displacements_si, reference.displacements_si, rtol=1e-12, atol=1e-12
    )
    np.testing.assert_allclose(
        result.reactions_si, reference.reactions_si, rtol=1e-12, atol=1e-8
    )
    np.testing.assert_allclose(
        result.element_end_forces_local_si,
        reference.element_end_forces_local_si,
        rtol=1e-12,
        atol=1e-8,
    )


def test_rotated_frame_sparse_residual_jvp_and_solve_match_v1() -> None:
    payload = _payload()
    payload["nodes"][1]["coordinates_m"] = [1.0, 2.0, 3.0]
    payload["elements"][0]["local_axis_rotation_rad"] = 0.37
    buffers = _buffers(payload, "LC_WEAK")
    reference_operator = assemble_linear_static_operator(buffers)
    reference_result = solve_linear_static(buffers, matrix_backend="dense")
    plan = compile_execution_plan_v2(buffers)
    result = solve_sparse_execution_plan_v2(plan)
    displacement = np.linspace(-2.0e-5, 3.0e-5, plan.dof_count)
    direction = np.linspace(1.0, 2.0, plan.dof_count)

    np.testing.assert_allclose(
        plan.residual(displacement),
        reference_operator.residual(displacement),
        rtol=1e-12,
        atol=1e-8,
    )
    np.testing.assert_allclose(
        plan.jvp(direction), reference_operator.jvp(direction), rtol=1e-12, atol=1e-6
    )
    reduced = sparse_reduced_jvp(plan, direction[plan.array("free_dofs")])
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    np.testing.assert_allclose(
        reduced,
        reference_operator.stiffness_matrix[np.ix_(free, free)] @ direction[free],
        rtol=1e-12,
        atol=1e-6,
    )
    np.testing.assert_allclose(
        result.displacements_si,
        reference_result.displacements_si,
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        result.reactions_si, reference_result.reactions_si, rtol=1e-12, atol=1e-8
    )


def test_five_size_chain_retained_plan_array_bytes_are_linear_without_v1_dense_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import structural_analysis.engine_v2.backends.cpu_reference.linear_static as v1_module

    def forbidden_dense_assembler(*args, **kwargs):
        raise AssertionError("v1 dense assembler must not run during sparse scaling")

    monkeypatch.setattr(
        v1_module, "assemble_linear_static_operator", forbidden_dense_assembler
    )
    node_counts = np.asarray([17, 33, 65, 129, 257], dtype=float)
    byte_lengths: list[int] = []
    nnz_values: list[int] = []
    for node_count in node_counts.astype(int):
        plan = compile_execution_plan_v2(_buffers(_chain_payload(node_count)))
        byte_lengths.append(plan.described_array_byte_length)
        nnz_values.append(plan.nnz)
        assert all(
            array.shape != (plan.dof_count, plan.dof_count) for array in plan._arrays
        )

    memory_slope = float(
        np.polyfit(np.log(node_counts), np.log(np.asarray(byte_lengths)), 1)[0]
    )
    nnz_slope = float(
        np.polyfit(np.log(node_counts), np.log(np.asarray(nnz_values)), 1)[0]
    )
    assert 0.9 <= memory_slope <= 1.1
    assert 0.9 <= nnz_slope <= 1.1
    assert byte_lengths == sorted(byte_lengths)


def test_sparse_v2_modules_do_not_call_global_densification_helpers() -> None:
    plan_source = (
        REPO_ROOT / "src/structural_analysis/engine_v2/contracts/execution_plan_v2.py"
    ).read_text(encoding="utf-8")
    solver_source = (
        REPO_ROOT
        / "src/structural_analysis/engine_v2/operators/sparse_linear_static.py"
    ).read_text(encoding="utf-8")
    combined = plan_source + solver_source

    assert ".toarray(" not in combined
    assert "assemble_linear_static_operator" not in combined
    assert "global_stiffness_dense" not in combined
