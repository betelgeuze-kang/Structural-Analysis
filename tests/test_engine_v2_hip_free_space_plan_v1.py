from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.free_space_plan import (
    HIP_FREE_SPACE_OPERATOR_PLAN_V1_CAPABILITY_PROFILE,
    HIP_FREE_SPACE_OPERATOR_PLAN_V1_SCHEMA_VERSION,
    HipFreeSpaceOperatorPlanV1Error,
    _ARRAY_NAMES,
    _array_descriptor,
    _free_space_view_hash,
    _plan_hash,
    _plan_id,
    compile_hip_free_space_operator_plan_v1,
    validate_hip_free_space_operator_plan_v1,
)
from structural_analysis.engine_v2.buffers import pack_solver_model_buffers
from structural_analysis.engine_v2.contracts._canonical import immutable_array
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    compile_execution_plan_v2,
)
from structural_analysis.model_ir import load_model_ir_v2, parse_model_ir_v2

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = (
    ROOT / "src/structural_analysis/schemas/hip_free_space_operator_plan_v1.schema.json"
)


def _payload() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _plan(
    payload: dict[str, Any] | None = None,
    *,
    load_pattern_id: str = "LC_AXIAL",
):
    model = load_model_ir_v2(FIXTURE) if payload is None else parse_model_ir_v2(payload)
    buffers = pack_solver_model_buffers(model, load_pattern_id=load_pattern_id)
    return compile_execution_plan_v2(buffers)


def _source_descriptor(plan: Any, name: str) -> Any:
    return next(row for row in plan.descriptors if row.name == name)


def _rehash(artifact: Any) -> Any:
    forged = replace(
        artifact,
        free_space_view_hash=_free_space_view_hash(artifact),
    )
    forged = replace(forged, plan_id=_plan_id(forged), plan_hash="sha256:" + "0" * 64)
    return replace(forged, plan_hash=_plan_hash(forged))


def _replace_arrays(artifact: Any, **updates: np.ndarray) -> Any:
    arrays = {name: artifact.array(name) for name in _ARRAY_NAMES}
    arrays.update(updates)
    descriptors = tuple(_array_descriptor(name, arrays[name]) for name in _ARRAY_NAMES)
    return _rehash(
        replace(
            artifact,
            descriptors=descriptors,
            _arrays=tuple(arrays[name] for name in _ARRAY_NAMES),
        )
    )


def _derive_reduced_for_free(plan: Any, free: np.ndarray) -> dict[str, np.ndarray]:
    global_to_free = np.full(plan.dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    full_row_ptr = plan.array("csr_row_ptr")
    full_columns = plan.array("csr_column_indices")
    row_ptr = [0]
    columns: list[int] = []
    mapping: list[int] = []
    for global_row_value in free:
        global_row = int(global_row_value)
        for position in range(
            int(full_row_ptr[global_row]), int(full_row_ptr[global_row + 1])
        ):
            reduced_column = int(global_to_free[int(full_columns[position])])
            if reduced_column >= 0:
                columns.append(reduced_column)
                mapping.append(position)
        row_ptr.append(len(columns))
    return {
        "free_dofs": immutable_array(free, dtype="<i4"),
        "global_to_free": immutable_array(global_to_free, dtype="<i4"),
        "reduced_csr_row_ptr": immutable_array(row_ptr, dtype="<i4"),
        "reduced_csr_column_indices": immutable_array(columns, dtype="<i4"),
        "reduced_csr_global_value_indices": immutable_array(mapping, dtype="<i4"),
    }


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _all_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _all_keys(child)}
    return set()


def test_schema_is_strict_draft202012_and_overlay_is_explicitly_non_solver() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    source = _plan()
    artifact = compile_hip_free_space_operator_plan_v1(source)
    payload = artifact.to_dict()

    assert not list(validator.iter_errors(payload))
    assert artifact.schema_version == HIP_FREE_SPACE_OPERATOR_PLAN_V1_SCHEMA_VERSION
    assert (
        artifact.capability_profile
        == HIP_FREE_SPACE_OPERATOR_PLAN_V1_CAPABILITY_PROFILE
    )
    assert payload["source_contract"]["solver_policy"] == "scipy_sparse_direct"
    assert payload["overlay_policy"]["solver_role"] == "none"
    assert payload["overlay_policy"]["source_solver_policy_overridden"] is False
    assert payload["claim_boundary"]["solver_policy_overridden"] is False
    assert payload["claim_boundary"]["solver_ready"] is False

    forged = deepcopy(payload)
    forged["overlay_policy"]["linear_solver"] = "device_pcg"
    assert list(validator.iter_errors(forged))


def test_compiler_is_deterministic_exact_detached_immutable_and_hash_bound() -> None:
    source = _plan()
    first = compile_hip_free_space_operator_plan_v1(source)
    second = compile_hip_free_space_operator_plan_v1(source)

    assert first.to_dict() == second.to_dict()
    assert first.plan_hash == second.plan_hash
    assert first.free_space_view_hash == second.free_space_view_hash
    assert first.source_execution_plan_hash == source.plan_hash
    assert first.source_operator_hash == source.operator_hash
    assert first.source_numeric_snapshot_hash == source.numeric_snapshot_hash
    assert first.source_symbolic_reuse_hash == source.symbolic_reuse_hash
    assert first.source_partition_hash == source.partition_hash
    assert first.global_dof_count == source.dof_count
    assert first.free_dof_count == len(source.free_dofs)
    assert first.full_csr_nnz == source.nnz
    assert first.reduced_csr_nnz == source.reduced_nnz

    for descriptor in first.descriptors:
        array = first.array(descriptor.name)
        source_array = source.array(descriptor.name)
        assert np.array_equal(array, source_array)
        assert (
            descriptor.to_dict()
            == _source_descriptor(source, descriptor.name).to_dict()
        )
        assert not np.shares_memory(array, source_array)
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)
    for left, left_name in enumerate(_ARRAY_NAMES):
        for right_name in _ARRAY_NAMES[left + 1 :]:
            assert not np.shares_memory(first.array(left_name), first.array(right_name))


def test_symbolic_payload_has_exact_five_arrays_and_numeric_is_oracle_only() -> None:
    source = _plan()
    artifact = compile_hip_free_space_operator_plan_v1(source)
    payload = artifact.to_dict()
    symbolic = payload["symbolic_payload"]

    assert tuple(row["name"] for row in symbolic["arrays"]) == _ARRAY_NAMES
    assert symbolic["array_order"] == list(_ARRAY_NAMES)
    assert symbolic["device_h2d_role"] == "symbolic_only"
    assert symbolic["reduced_numeric_values_present"] is False
    assert symbolic["reduced_numeric_values_h2d_forbidden"] is True
    assert "values" not in _all_keys(symbolic)
    assert "reduced_stiffness_csr_values" not in {
        row["name"] for row in symbolic["arrays"]
    }

    oracle = artifact.verification_oracle
    source_oracle = _source_descriptor(source, "reduced_stiffness_csr_values")
    assert oracle.source_array_name == "reduced_stiffness_csr_values"
    assert oracle.data_hash == source_oracle.data_hash
    assert oracle.content_hash == source_oracle.content_hash
    assert oracle.byte_length == source_oracle.byte_length
    assert oracle.device_upload_forbidden is True
    assert oracle.role == "verification_oracle_only_never_device_input"


def test_full_to_reduced_mapping_materializes_exact_cpu_oracle_values() -> None:
    source = _plan()
    artifact = compile_hip_free_space_operator_plan_v1(source)
    mapping = artifact.array("reduced_csr_global_value_indices")
    gathered = source.array("global_stiffness_csr_values")[mapping]

    assert np.array_equal(gathered, source.array("reduced_stiffness_csr_values"))
    assert (
        artifact.verification_oracle.data_hash
        == _source_descriptor(source, "reduced_stiffness_csr_values").data_hash
    )
    assert np.all(np.diff(mapping.astype(np.int64, copy=False)) > 0)
    row_ptr = artifact.array("reduced_csr_row_ptr")
    columns = artifact.array("reduced_csr_column_indices")
    for row in range(artifact.free_dof_count):
        row_columns = columns[int(row_ptr[row]) : int(row_ptr[row + 1])]
        assert np.count_nonzero(row_columns == row) == 1
        assert np.all(np.diff(row_columns.astype(np.int64, copy=False)) > 0)


def test_noncontiguous_free_partition_is_rederived_without_contiguous_assumption() -> (
    None
):
    payload = _payload()
    payload["constraints"][0]["dofs"] = ["UX", "UZ", "RY"]
    payload["constraints"][0]["prescribed_values_si"] = {
        "UX": 0.0,
        "UZ": 0.0,
        "RY": 0.0,
    }
    source = _plan(payload)
    artifact = compile_hip_free_space_operator_plan_v1(source)
    free = artifact.array("free_dofs")

    assert free.tolist() == [1, 3, 5, 6, 7, 8, 9, 10, 11]
    assert np.array_equal(
        artifact.array("global_to_free")[free],
        np.arange(free.size, dtype="<i4"),
    )
    assert np.array_equal(
        source.array("global_stiffness_csr_values")[
            artifact.array("reduced_csr_global_value_indices")
        ],
        source.array("reduced_stiffness_csr_values"),
    )


def test_symbolic_bytes_can_reuse_topology_but_view_binds_numeric_source() -> None:
    axial = _plan(load_pattern_id="LC_AXIAL")
    weak = _plan(load_pattern_id="LC_WEAK")
    axial_overlay = compile_hip_free_space_operator_plan_v1(axial)
    weak_overlay = compile_hip_free_space_operator_plan_v1(weak)

    assert axial.symbolic_reuse_hash == weak.symbolic_reuse_hash
    for name in _ARRAY_NAMES:
        assert np.array_equal(axial_overlay.array(name), weak_overlay.array(name))
    assert (
        axial_overlay.source_numeric_snapshot_hash
        != weak_overlay.source_numeric_snapshot_hash
    )
    assert axial_overlay.source_operator_hash != weak_overlay.source_operator_hash
    assert axial_overlay.free_space_view_hash != weak_overlay.free_space_view_hash
    assert axial_overlay.plan_hash != weak_overlay.plan_hash


def test_fully_rehashed_coherent_partition_forgery_is_rejected_by_source_binding() -> (
    None
):
    source = _plan()
    artifact = compile_hip_free_space_operator_plan_v1(source)
    forged_free = np.asarray([5, 7, 8, 9, 10, 11], dtype="<i4")
    forged_arrays = _derive_reduced_for_free(source, forged_free)
    forged = _replace_arrays(artifact, **forged_arrays)

    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as caught:
        validate_hip_free_space_operator_plan_v1(forged)
    assert caught.value.code in {
        "hip_free_space_source_descriptor_mismatch",
        "hip_free_space_source_rederivation_mismatch",
    }


def test_fully_rehashed_oracle_and_source_hash_forgeries_are_rejected() -> None:
    source = _plan()
    artifact = compile_hip_free_space_operator_plan_v1(source)
    forged_oracle = replace(
        artifact.verification_oracle,
        data_hash="sha256:" + "e" * 64,
    )
    oracle_forgery = _rehash(replace(artifact, verification_oracle=forged_oracle))
    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as oracle_error:
        validate_hip_free_space_operator_plan_v1(oracle_forgery)
    assert oracle_error.value.code == "hip_free_space_oracle_binding_mismatch"

    source_forgery = _rehash(
        replace(artifact, source_operator_hash="sha256:" + "d" * 64)
    )
    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as source_error:
        validate_hip_free_space_operator_plan_v1(source_forgery)
    assert source_error.value.code == "hip_free_space_source_binding_mismatch"


def test_equal_source_array_alias_is_rejected_even_with_unchanged_hashes() -> None:
    artifact = compile_hip_free_space_operator_plan_v1(_plan())
    arrays = list(artifact._arrays)
    arrays[0] = artifact._source_execution_plan.array("free_dofs")
    forged = replace(artifact, _arrays=tuple(arrays))

    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as caught:
        validate_hip_free_space_operator_plan_v1(forged)
    assert caught.value.code == "hip_free_space_array_alias_invalid"


def test_bool_int_ndarray_subclass_and_mutable_container_forgeries_fail_closed() -> (
    None
):
    artifact = compile_hip_free_space_operator_plan_v1(_plan())
    bool_dimension = _rehash(replace(artifact, free_dof_count=True))
    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as bool_error:
        validate_hip_free_space_operator_plan_v1(bool_dimension)
    assert bool_error.value.code in {
        "hip_free_space_plan_schema_invalid",
        "hip_free_space_dimension_invalid",
    }

    class ArraySubclass(np.ndarray):
        pass

    arrays = list(artifact._arrays)
    arrays[0] = arrays[0].view(ArraySubclass)
    subclass_forgery = replace(artifact, _arrays=tuple(arrays))
    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as subclass_error:
        validate_hip_free_space_operator_plan_v1(subclass_forgery)
    assert subclass_error.value.code == "hip_free_space_plan_container_invalid"

    mutable_descriptor_container = replace(
        artifact,
        descriptors=list(artifact.descriptors),  # type: ignore[arg-type]
    )
    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as container_error:
        validate_hip_free_space_operator_plan_v1(mutable_descriptor_container)
    assert container_error.value.code == "hip_free_space_plan_container_invalid"


def test_caller_plan_field_swap_after_compile_cannot_change_retained_witness() -> None:
    source = _plan()
    artifact = compile_hip_free_space_operator_plan_v1(source)
    original_manifest = artifact.to_dict()
    object.__setattr__(source, "plan_hash", "sha256:" + "f" * 64)

    validate_hip_free_space_operator_plan_v1(artifact)
    assert artifact.to_dict() == original_manifest
    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as caught:
        validate_hip_free_space_operator_plan_v1(
            artifact, expected_execution_plan=source
        )
    assert caught.value.code == "hip_free_space_source_plan_invalid"


def test_caller_descriptor_mutation_after_compile_cannot_change_retained_witness() -> (
    None
):
    source = _plan()
    artifact = compile_hip_free_space_operator_plan_v1(source)
    original_manifest = artifact.to_dict()
    object.__setattr__(
        source.descriptors[0],
        "data_hash",
        "sha256:" + "c" * 64,
    )
    object.__setattr__(
        source._source_buffers.descriptors[0],
        "data_hash",
        "sha256:" + "b" * 64,
    )

    validate_hip_free_space_operator_plan_v1(artifact)
    assert artifact.to_dict() == original_manifest


def test_cross_plan_expected_binding_and_invalid_source_fail_before_artifact() -> None:
    source = _plan(load_pattern_id="LC_AXIAL")
    other = _plan(load_pattern_id="LC_WEAK")
    artifact = compile_hip_free_space_operator_plan_v1(source)

    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as cross_error:
        validate_hip_free_space_operator_plan_v1(
            artifact, expected_execution_plan=other
        )
    assert cross_error.value.code == "hip_free_space_source_binding_mismatch"

    invalid_source = replace(source, operator_hash="sha256:" + "a" * 64)
    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as invalid_error:
        compile_hip_free_space_operator_plan_v1(invalid_source)
    assert invalid_error.value.code == "hip_free_space_source_plan_invalid"


def test_descriptor_byte_formula_excludes_cpu_numeric_oracle_bytes() -> None:
    artifact = compile_hip_free_space_operator_plan_v1(_plan())
    g = artifact.global_dof_count
    f = artifact.free_dof_count
    zf = artifact.reduced_csr_nnz
    expected_symbolic_bytes = 4 * (f + g + (f + 1) + zf + zf)

    assert artifact.described_array_byte_length == expected_symbolic_bytes
    assert artifact.verification_oracle.byte_length == 8 * zf
    assert (
        artifact.described_array_byte_length
        != expected_symbolic_bytes + artifact.verification_oracle.byte_length
    )


def test_oracle_binding_exact_type_is_required() -> None:
    artifact = compile_hip_free_space_operator_plan_v1(_plan())
    forged = replace(
        artifact,
        verification_oracle={  # type: ignore[arg-type]
            **artifact.verification_oracle.to_dict(),
        },
    )
    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as caught:
        validate_hip_free_space_operator_plan_v1(forged)
    assert caught.value.code == "hip_free_space_plan_container_invalid"


def test_oracle_dataclass_rejects_boolean_upload_claim_in_schema_after_rehash() -> None:
    artifact = compile_hip_free_space_operator_plan_v1(_plan())
    forged_oracle = replace(
        artifact.verification_oracle,
        device_upload_forbidden=1,  # type: ignore[arg-type]
    )
    forged = _rehash(replace(artifact, verification_oracle=forged_oracle))
    with pytest.raises(HipFreeSpaceOperatorPlanV1Error) as caught:
        validate_hip_free_space_operator_plan_v1(forged)
    assert caught.value.code == "hip_free_space_plan_schema_invalid"
