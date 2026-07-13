from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import math
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

from structural_analysis.engine_v2.assembly_backend.plan import (  # noqa: E402
    REFERENCE_AXIS_GLOBAL_Y,
    REFERENCE_AXIS_GLOBAL_Z,
    HipAssemblyPlanV1Error,
    _array_descriptor,
    _assembly_plan_hash,
    _assembly_plan_id,
    _axis_policy_hash,
    _compile_reverse_map,
    _detached_immutable_array,
    _guard_dimensions,
    _reverse_map_hash,
    _symbolic_payload_hash,
    compile_hip_assembly_plan_v1,
    validate_hip_assembly_plan_v1,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    has_immutable_bytes_backing,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.model_ir import parse_model_ir_v2  # noqa: E402


FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = REPO_ROOT / "src/structural_analysis/schemas/hip_assembly_plan_v1.schema.json"
ARRAY_NAMES = (
    "reference_axis_code",
    "reverse_segment_offsets",
    "reverse_contribution_indices",
)
INT32_MAX = int(np.iinfo(np.int32).max)


def _payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _buffers(payload: dict | None = None, *, load_pattern_id: str = "LC_AXIAL"):
    return pack_solver_model_buffers(
        parse_model_ir_v2(_payload() if payload is None else payload),
        load_pattern_id=load_pattern_id,
    )


def _sources(payload: dict | None = None, *, load_pattern_id: str = "LC_AXIAL"):
    buffers = _buffers(payload, load_pattern_id=load_pattern_id)
    return buffers, compile_execution_plan_v2(buffers)


def _artifact(payload: dict | None = None, *, load_pattern_id: str = "LC_AXIAL"):
    buffers, execution_plan = _sources(payload, load_pattern_id=load_pattern_id)
    return (
        buffers,
        execution_plan,
        compile_hip_assembly_plan_v1(buffers, execution_plan),
    )


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


def _isolated_node_payload() -> dict:
    payload = _payload()
    payload["nodes"].append(
        {
            "id": "N3",
            "index": 2,
            "coordinates_m": [9.0, 4.0, 1.0],
            "source_id": "generated:N3",
            "extensions": {},
        }
    )
    return payload


def _replace_arrays(artifact, **updates):
    arrays = {name: artifact.array(name) for name in ARRAY_NAMES}
    arrays.update(updates)
    descriptors = tuple(_array_descriptor(name, arrays[name]) for name in ARRAY_NAMES)
    forged = replace(
        artifact,
        descriptors=descriptors,
        _arrays=tuple(arrays[name] for name in ARRAY_NAMES),
    )
    descriptor_map = {row.name: row for row in descriptors}
    forged = replace(
        forged,
        axis_policy_hash=_axis_policy_hash(forged, descriptor_map),
        reverse_map_hash=_reverse_map_hash(forged, descriptor_map),
    )
    forged = replace(
        forged,
        symbolic_payload_hash=_symbolic_payload_hash(forged, descriptor_map),
    )
    forged = replace(forged, assembly_plan_id=_assembly_plan_id(forged))
    return replace(forged, assembly_plan_hash=_assembly_plan_hash(forged))


def _fully_rehash_metadata(artifact, **updates):
    forged = replace(artifact, **updates)
    descriptor_map = {row.name: row for row in forged.descriptors}
    forged = replace(
        forged,
        axis_policy_hash=_axis_policy_hash(forged, descriptor_map),
        reverse_map_hash=_reverse_map_hash(forged, descriptor_map),
    )
    forged = replace(
        forged,
        symbolic_payload_hash=_symbolic_payload_hash(forged, descriptor_map),
    )
    forged = replace(forged, assembly_plan_id=_assembly_plan_id(forged))
    return replace(forged, assembly_plan_hash=_assembly_plan_hash(forged))


def test_schema_is_strict_draft202012_and_manifest_contains_no_csr_numeric_values() -> (
    None
):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    _, _, artifact = _artifact()
    manifest = artifact.to_dict()

    assert not list(validator.iter_errors(manifest))
    assert "global_stiffness_csr_values" not in json.dumps(manifest, sort_keys=True)
    assert manifest["symbolic_payload"]["csr_numeric_values_present"] is False
    assert manifest["claim_boundary"] == {
        "compiler_location": "cpu",
        "reverse_compile_complexity": "O(C+Z)_fixed_12x12_scatter",
        "manifest_serialization_complexity": (
            "O(C+Z)_with_high_transient_python_object_memory"
        ),
        "contribution_formula": "C=144E",
        "global_dense_matrix_materialized": False,
        "csr_numeric_values_copied_or_described": False,
        "hip_execution_performed": False,
        "device_allocation_performed": False,
        "numerical_assembly_performed": False,
        "solver_ready": False,
        "end_to_end_O_N_claim": False,
        "commercial_solver_parity_claim": False,
    }

    extra = deepcopy(manifest)
    extra["symbolic_payload"]["csr_values"] = [1.0]
    assert list(validator.iter_errors(extra))
    extra = deepcopy(manifest)
    extra["source_contract"]["unbound_pointer"] = "0x1234"
    assert list(validator.iter_errors(extra))
    invalid_code = deepcopy(manifest)
    invalid_code["axis_policy"]["reference_axis_code"][0] = 0
    assert list(validator.iter_errors(invalid_code))


def test_compiler_is_deterministic_exact_immutable_alias_free_and_fully_bound() -> None:
    buffers, execution_plan = _sources()
    first = compile_hip_assembly_plan_v1(buffers, execution_plan)
    second = compile_hip_assembly_plan_v1(buffers, execution_plan)

    assert first.to_dict() == second.to_dict()
    assert first.assembly_plan_hash == second.assembly_plan_hash
    assert first.symbolic_payload_hash == second.symbolic_payload_hash
    assert first.contribution_count == 144 * first.element_count
    assert first.contributions_per_element == 144
    assert first.csr_nnz == execution_plan.nnz
    assert first.source_execution_plan_hash == execution_plan.plan_hash
    assert first.solver_artifact_hash == buffers.artifact_hash
    assert first.array("reference_axis_code").tolist() == [REFERENCE_AXIS_GLOBAL_Z]
    assert type(first.descriptors) is tuple
    assert type(first._arrays) is tuple

    arrays = list(first._arrays)
    for array in arrays:
        assert type(array) is np.ndarray
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        assert has_immutable_bytes_backing(array)
        with pytest.raises(ValueError):
            array.setflags(write=True)
    for left in range(len(arrays)):
        for right in range(left + 1, len(arrays)):
            assert not np.shares_memory(arrays[left], arrays[right])
    for array in arrays:
        assert all(
            not np.shares_memory(array, source) for source in execution_plan._arrays
        )
        assert all(
            not np.shares_memory(array, buffers.array(row.name))
            for row in buffers.descriptors
        )


@pytest.mark.parametrize(
    ("coordinates", "expected_code"),
    [
        ([math.sqrt(19.0), 0.0, 9.0], REFERENCE_AXIS_GLOBAL_Z),
        ([math.sqrt(1.0 - 0.91**2), 0.0, 0.91], REFERENCE_AXIS_GLOBAL_Y),
        ([0.0, 0.0, -2.0], REFERENCE_AXIS_GLOBAL_Y),
    ],
)
def test_reference_axis_uses_strict_0_9_cpu_boundary_and_kernel_codes(
    coordinates: list[float], expected_code: int
) -> None:
    payload = _payload()
    payload["nodes"][1]["coordinates_m"] = coordinates
    _, _, artifact = _artifact(payload)
    assert artifact.array("reference_axis_code").tolist() == [expected_code]
    validate_hip_assembly_plan_v1(artifact)

    if coordinates[2] == 9.0:
        vector = np.asarray(coordinates, dtype="<f8")
        assert float(vector[2] / np.linalg.norm(vector)) == 0.9
        assert expected_code == REFERENCE_AXIS_GLOBAL_Z


def test_reverse_map_preserves_multi_element_collision_order_exactly() -> None:
    _, execution_plan, artifact = _artifact(_two_element_payload())
    scatter = execution_plan.array("csr_element_scatter_indices").reshape(-1)
    offsets = artifact.array("reverse_segment_offsets")
    reverse = artifact.array("reverse_contribution_indices")
    collision_across_elements = False

    for target in range(artifact.csr_nnz):
        expected = np.flatnonzero(scatter == target).astype("<i4", copy=False)
        actual = reverse[int(offsets[target]) : int(offsets[target + 1])]
        assert np.array_equal(actual, expected)
        if expected.size and int(expected[0]) < 144 <= int(expected[-1]):
            collision_across_elements = True
            assert np.all(np.diff(actual) > 0)
    assert collision_across_elements
    assert int(offsets[-1]) == 288


def test_reverse_map_retains_structural_zero_and_empty_csr_segments() -> None:
    _, execution_plan, artifact = _artifact(_isolated_node_payload())
    scatter = execution_plan.array("csr_element_scatter_indices").reshape(-1)
    counts = np.bincount(scatter, minlength=artifact.csr_nnz)
    offsets = artifact.array("reverse_segment_offsets")
    values = execution_plan.array("global_stiffness_csr_values")

    empty = np.flatnonzero(counts == 0)
    assert empty.size == 6
    for target in empty:
        assert int(offsets[target]) == int(offsets[target + 1])
    assert np.any((values == 0.0) & (counts > 0))
    assert (
        artifact.to_dict()["reverse_assembly_plan"]["structural_zero_segments_retained"]
        is True
    )


def test_linear_reverse_compiler_supports_empty_segments_without_sorting() -> None:
    scatter = np.empty((1, 12, 12), dtype="<i4")
    scatter.reshape(-1)[:] = np.arange(144, dtype="<i4") % 2 * 2
    offsets, reverse = _compile_reverse_map(scatter, csr_nnz=4)
    assert offsets.tolist() == [0, 72, 72, 144, 144]
    assert reverse[:72].tolist() == list(range(0, 144, 2))
    assert reverse[72:].tolist() == list(range(1, 144, 2))


def test_fully_rehashed_axis_tamper_is_rejected_by_independent_cpu_rederivation() -> (
    None
):
    _, _, artifact = _artifact()
    changed = _detached_immutable_array([REFERENCE_AXIS_GLOBAL_Y], dtype="u1")
    forged = _replace_arrays(artifact, reference_axis_code=changed)
    assert forged.assembly_plan_hash != artifact.assembly_plan_hash
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_axis_rederivation_mismatch"


def test_fully_rehashed_duplicate_reverse_index_is_rejected() -> None:
    _, _, artifact = _artifact(_two_element_payload())
    offsets = artifact.array("reverse_segment_offsets")
    target = next(
        index
        for index in range(artifact.csr_nnz)
        if int(offsets[index + 1]) - int(offsets[index]) >= 2
    )
    changed = artifact.array("reverse_contribution_indices").copy()
    start = int(offsets[target])
    changed[start + 1] = changed[start]
    forged = _replace_arrays(
        artifact,
        reverse_contribution_indices=_detached_immutable_array(changed, dtype="<i4"),
    )
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_reverse_index_duplicate"


@pytest.mark.parametrize("bad_index", [-1, 144])
def test_fully_rehashed_signed_or_out_of_range_reverse_index_is_rejected(
    bad_index: int,
) -> None:
    _, _, artifact = _artifact()
    changed = artifact.array("reverse_contribution_indices").copy()
    changed[0] = bad_index
    forged = _replace_arrays(
        artifact,
        reverse_contribution_indices=_detached_immutable_array(changed, dtype="<i4"),
    )
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code in {
        "hip_assembly_plan_schema_invalid",
        "hip_assembly_plan_reverse_index_range_invalid",
    }


def test_fully_rehashed_reverse_order_tamper_is_rejected() -> None:
    _, _, artifact = _artifact(_two_element_payload())
    offsets = artifact.array("reverse_segment_offsets")
    target = next(
        index
        for index in range(artifact.csr_nnz)
        if int(offsets[index + 1]) - int(offsets[index]) >= 2
    )
    changed = artifact.array("reverse_contribution_indices").copy()
    start = int(offsets[target])
    changed[start], changed[start + 1] = changed[start + 1], changed[start]
    forged = _replace_arrays(
        artifact,
        reverse_contribution_indices=_detached_immutable_array(changed, dtype="<i4"),
    )
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_reverse_order_invalid"


def test_fully_rehashed_source_geometry_and_support_claims_cannot_be_forged() -> None:
    _, _, artifact = _artifact()
    fake_hash = "sha256:" + "1" * 64
    forged = _fully_rehash_metadata(artifact, source_geometry_hash=fake_hash)
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_source_execution_plan_mismatch"

    forged = _fully_rehash_metadata(artifact, source_support_partition_hash=fake_hash)
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_source_execution_plan_mismatch"


def test_mutable_arrays_ndarray_subclasses_and_mutable_containers_are_rejected() -> (
    None
):
    _, _, artifact = _artifact()
    mutable = artifact.array("reverse_contribution_indices").copy()
    forged = _replace_arrays(artifact, reverse_contribution_indices=mutable)
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_array_storage_invalid"

    class ArraySubclass(np.ndarray):
        pass

    subclass = artifact.array("reference_axis_code").view(ArraySubclass)
    forged = replace(
        artifact,
        _arrays=(subclass, *artifact._arrays[1:]),
    )
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_container_invalid"

    forged = replace(artifact, descriptors=list(artifact.descriptors))
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_container_invalid"
    forged = replace(artifact, _arrays=list(artifact._arrays))
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_container_invalid"


def test_reusing_equal_source_bytes_is_rejected_as_alias_even_after_full_rehash() -> (
    None
):
    buffers, _, artifact = _artifact()
    source_element_type = buffers.array("element_type")
    assert source_element_type.tolist() == [REFERENCE_AXIS_GLOBAL_Z]
    forged = _replace_arrays(artifact, reference_axis_code=source_element_type)
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_array_alias_invalid"


def test_compiler_detaches_caller_mapping_proxy_backing_before_retaining_sources() -> (
    None
):
    buffers = _buffers()
    external_arrays = {row.name: buffers.array(row.name) for row in buffers.descriptors}
    caller_owned = replace(
        buffers,
        _arrays=MappingProxyType(external_arrays),
    )
    execution_plan = compile_execution_plan_v2(caller_owned)
    artifact = compile_hip_assembly_plan_v1(caller_owned, execution_plan)
    before_manifest = artifact.to_dict()
    before_coordinates = artifact._source_buffers.array("node_coordinates_m").copy()

    changed_coordinates = caller_owned.array("node_coordinates_m").copy()
    changed_coordinates[0, 0] = 3.0
    external_arrays["node_coordinates_m"] = _detached_immutable_array(
        changed_coordinates,
        dtype="<f8",
    )

    assert artifact._source_buffers is not caller_owned
    assert artifact._source_execution_plan is not execution_plan
    assert "global_stiffness_csr_values" not in repr(artifact)
    assert np.array_equal(
        artifact._source_buffers.array("node_coordinates_m"),
        before_coordinates,
    )
    assert artifact.to_dict() == before_manifest
    validate_hip_assembly_plan_v1(artifact)


def test_stale_descriptor_and_aggregate_hashes_are_rejected() -> None:
    _, _, artifact = _artifact()
    changed = _detached_immutable_array([REFERENCE_AXIS_GLOBAL_Y], dtype="u1")
    stale_descriptor = replace(
        artifact,
        _arrays=(changed, *artifact._arrays[1:]),
    )
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(stale_descriptor)
    assert caught.value.code == "hip_assembly_plan_array_descriptor_mismatch"

    stale_hash = replace(artifact, assembly_plan_hash="sha256:" + "f" * 64)
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(stale_hash)
    assert caught.value.code == "hip_assembly_plan_hash_mismatch"


def test_expected_plan_buffer_and_retained_source_mismatches_fail_closed() -> None:
    buffers, execution_plan, artifact = _artifact()
    other_buffers, other_plan = _sources(load_pattern_id="LC_WEAK")

    validate_hip_assembly_plan_v1(
        artifact,
        expected_buffers=buffers,
        expected_execution_plan=execution_plan,
    )
    with pytest.raises(HipAssemblyPlanV1Error):
        validate_hip_assembly_plan_v1(artifact, expected_buffers=other_buffers)
    with pytest.raises(HipAssemblyPlanV1Error):
        validate_hip_assembly_plan_v1(
            artifact,
            expected_buffers=other_buffers,
            expected_execution_plan=other_plan,
        )

    forged = replace(artifact, _source_buffers=other_buffers)
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        validate_hip_assembly_plan_v1(forged)
    assert caught.value.code == "hip_assembly_plan_source_execution_plan_invalid"


def test_int32_capacity_and_scatter_signed_range_guards_fail_before_allocation() -> (
    None
):
    assert (
        _guard_dimensions(node_count=1, element_count=1, dof_count=6, csr_nnz=1) == 144
    )
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        _guard_dimensions(
            node_count=1,
            element_count=INT32_MAX // 144 + 1,
            dof_count=6,
            csr_nnz=1,
        )
    assert caught.value.code == "hip_assembly_plan_int32_capacity_exceeded"
    assert caught.value.path == "/dimensions/contribution_count"

    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        _guard_dimensions(
            node_count=1,
            element_count=3_721_809,
            dof_count=6,
            csr_nnz=1,
        )
    assert caught.value.code == "hip_assembly_plan_int32_capacity_exceeded"
    assert caught.value.path == "/dimensions/symbolic_payload_byte_length"

    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        _guard_dimensions(
            node_count=1,
            element_count=1,
            dof_count=6,
            csr_nnz=INT32_MAX,
        )
    assert caught.value.code == "hip_assembly_plan_int32_capacity_exceeded"
    assert caught.value.path == "/dimensions/reverse_segment_offsets"

    negative = np.zeros((1, 12, 12), dtype="<i4")
    negative[0, 0, 0] = -1
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        _compile_reverse_map(negative, csr_nnz=1)
    assert caught.value.code == "hip_assembly_plan_scatter_range_invalid"

    too_large = np.zeros((1, 12, 12), dtype="<i4")
    too_large[0, 0, 0] = 2
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        _compile_reverse_map(too_large, csr_nnz=2)
    assert caught.value.code == "hip_assembly_plan_scatter_range_invalid"


def test_compile_requires_exact_hardened_sources() -> None:
    buffers, execution_plan = _sources()
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        compile_hip_assembly_plan_v1(object(), execution_plan)  # type: ignore[arg-type]
    assert caught.value.code == "hip_assembly_plan_source_buffer_invalid"
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        compile_hip_assembly_plan_v1(buffers, object())  # type: ignore[arg-type]
    assert caught.value.code == "hip_assembly_plan_source_execution_plan_invalid"

    tampered_source = replace(
        execution_plan,
        _arrays=list(execution_plan._arrays),
    )
    with pytest.raises(HipAssemblyPlanV1Error) as caught:
        compile_hip_assembly_plan_v1(buffers, tampered_source)
    assert caught.value.code == "hip_assembly_plan_source_execution_plan_invalid"
