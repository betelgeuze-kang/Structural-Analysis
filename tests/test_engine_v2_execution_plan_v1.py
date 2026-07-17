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

from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    EXECUTION_PLAN_SCHEMA_VERSION,
    ExecutionPlanError,
    create_execution_plan,
    validate_execution_plan,
    validate_execution_plan_manifest,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
)

SCHEMA = REPO_ROOT / "src/structural_analysis/schemas/execution_plan_v1.schema.json"


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _inputs() -> dict[str, object]:
    dof_count = 12
    return {
        "model_ir_content_hash": _hash("1"),
        "solver_buffer_schema_version": "solver-model-buffers.v1",
        "solver_numeric_buffer_hash": _hash("2"),
        "solver_entity_mapping_hash": _hash("3"),
        "solver_artifact_hash": _hash("4"),
        "load_pattern_id": "LC1",
        "operator_id": "linear-static-operator",
        "operator_version": "linear-static-operator.v1",
        "operator_hash": _hash("5"),
        "node_ids": ("N1", "N2"),
        "element_ids": ("E1",),
        "node_dof_indices": np.arange(dof_count, dtype="<i4").reshape(2, 6),
        "global_to_free": np.asarray(
            [-1, -1, -1, -1, -1, -1, 0, 1, 2, 3, 4, 5], dtype="<i4"
        ),
        "element_global_dofs": np.arange(dof_count, dtype="<i4").reshape(1, 12),
        "constrained_dofs": np.arange(6, dtype="<i4"),
        "free_dofs": np.arange(6, dof_count, dtype="<i4"),
        "csr_row_ptr": np.arange(0, dof_count * dof_count + 1, dof_count, dtype="<i8"),
        "csr_column_indices": np.tile(np.arange(dof_count, dtype="<i4"), dof_count),
    }


def _plan():
    return create_execution_plan(**_inputs())


def test_execution_plan_manifest_is_strict_deterministic_and_backend_neutral() -> None:
    first = _plan()
    second = _plan()
    manifest = first.to_dict()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert first.schema_version == EXECUTION_PLAN_SCHEMA_VERSION
    assert first.plan_hash == second.plan_hash
    assert manifest == second.to_dict()
    assert manifest["execution_policy"] == {
        "precision": "fp64",
        "fallback": "forbidden",
        "placement": "runtime_selected",
        "backend_binding": "external",
    }
    assert "backend" not in manifest
    assert "solver_policy" not in manifest
    assert "equation_scaling" not in manifest

    manifest["operator_graph"][0]["depends_on"].append("forged")
    assert _plan().to_dict()["operator_graph"][0]["depends_on"] == []


def test_plan_arrays_are_canonical_bytes_backed_and_content_addressed() -> None:
    first = _plan()
    second = _plan()

    for descriptor in first.descriptors:
        array = first.array(descriptor.name)
        assert array.dtype.str == descriptor.dtype
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        assert (
            descriptor
            == second.descriptors[
                [row.name for row in second.descriptors].index(descriptor.name)
            ]
        )
        with pytest.raises(ValueError):
            array.setflags(write=True)

    np.testing.assert_array_equal(
        first.array("node_dof_indices"), np.arange(12).reshape(2, 6)
    )
    assert first.constrained_dofs == tuple(range(6))
    assert first.free_dofs == tuple(range(6, 12))


@pytest.mark.parametrize(
    ("mutate", "path_fragment"),
    [
        (
            lambda payload: payload["analysis"].update({"device_pointer": "0x123"}),
            "/analysis",
        ),
        (
            lambda payload: payload["dof_layout"].update({"node_count": 2.0}),
            "/dof_layout/node_count",
        ),
        (
            lambda payload: payload["dof_layout"].update({"element_count": True}),
            "/dof_layout/element_count",
        ),
        (
            lambda payload: payload["array_descriptors"]["free_dofs"].update(
                {"byte_length": "24"}
            ),
            "/array_descriptors/free_dofs/byte_length",
        ),
    ],
)
def test_manifest_rejects_unknown_fields_and_wrong_exact_json_types(
    mutate, path_fragment: str
) -> None:
    payload = deepcopy(_plan().to_dict())
    mutate(payload)

    with pytest.raises(ExecutionPlanError) as error:
        validate_execution_plan_manifest(payload)

    assert error.value.code == "execution_plan_schema_invalid"
    assert path_fragment in error.value.path


def test_manifest_rejects_valid_shape_with_stale_aggregate_hash() -> None:
    payload = deepcopy(_plan().to_dict())
    payload["analysis"]["operator_id"] = "different-operator"

    with pytest.raises(ExecutionPlanError) as error:
        validate_execution_plan_manifest(payload)

    assert error.value.code == "plan_hash_mismatch"


def test_builder_rejects_float_and_boolean_index_collections() -> None:
    float_inputs = _inputs()
    float_inputs["free_dofs"] = [6.0, 7.0, 8.0, 9.0, 10.0, 11.0]
    with pytest.raises(ExecutionPlanError) as float_error:
        create_execution_plan(**float_inputs)
    assert float_error.value.code == "array_type_invalid"

    bool_inputs = _inputs()
    bool_inputs["constrained_dofs"] = [True, True, True, True, True, True]
    with pytest.raises(ExecutionPlanError) as bool_error:
        create_execution_plan(**bool_inputs)
    assert bool_error.value.code == "array_type_invalid"


def test_array_descriptor_pattern_and_partition_tampering_fail_closed() -> None:
    plan = _plan()
    forged_descriptor = replace(plan.descriptors[0], data_hash=_hash("f"))
    with pytest.raises(ExecutionPlanError) as descriptor_error:
        validate_execution_plan(
            replace(plan, descriptors=(forged_descriptor, *plan.descriptors[1:]))
        )
    assert descriptor_error.value.code == "array_descriptor_mismatch"

    with pytest.raises(ExecutionPlanError) as pattern_error:
        validate_execution_plan(replace(plan, pattern_hash=_hash("e")))
    assert pattern_error.value.code == "pattern_hash_mismatch"

    arrays = dict(plan._arrays)
    arrays["global_to_free"] = immutable_array(
        [-1, -1, -1, -1, -1, -1, 1, 0, 2, 3, 4, 5], dtype="<i4"
    )
    forged = replace(plan, _arrays=MappingProxyType(arrays))
    with pytest.raises(ExecutionPlanError) as mapping_error:
        validate_execution_plan(forged)
    assert mapping_error.value.code == "array_descriptor_mismatch"


def test_state_ir_binds_to_the_real_execution_plan_contract() -> None:
    plan = _plan()
    state = create_initial_state(plan)

    assert state.execution_plan_hash == plan.plan_hash
    assert state.model_ir_content_hash == plan.model_ir_content_hash
    assert state.operator_hash == plan.operator_hash
    assert state.dof_count == plan.dof_count
