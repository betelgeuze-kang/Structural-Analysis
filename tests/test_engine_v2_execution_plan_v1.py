from __future__ import annotations

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

from structural_analysis.engine_v2.buffers import pack_solver_model_buffers  # noqa: E402
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    ExecutionPlanError,
    _array_descriptor,
    compile_execution_plan,
    compute_recovery_operator_hash,
    validate_execution_plan,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = REPO_ROOT / "src/structural_analysis/schemas/execution_plan_v1.schema.json"


def _buffers(load_pattern_id: str = "LC_AXIAL"):
    return pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id=load_pattern_id
    )


def test_execution_plan_schema_and_compiled_manifest_are_strict() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    plan = compile_execution_plan(_buffers())

    assert not list(validator.iter_errors(plan.to_dict()))
    graph = plan.to_dict()["operator_graph"]
    assert [row["id"] for row in graph] == [
        "assembly",
        "partition",
        "solve",
        "residual",
        "reaction",
        "recovery",
        "energy",
    ]
    assert graph[3]["depends_on"] == ["assembly", "solve"]

    reordered = plan.to_dict()
    reordered["operator_graph"][0], reordered["operator_graph"][1] = (
        reordered["operator_graph"][1],
        reordered["operator_graph"][0],
    )
    assert list(validator.iter_errors(reordered))

    with_pointer = plan.to_dict()
    with_pointer["backend_policy"]["device_pointer"] = "0x1234"
    assert list(validator.iter_errors(with_pointer))


def test_execution_plan_is_deterministic_and_all_payloads_are_bytes_backed() -> None:
    first = compile_execution_plan(_buffers())
    second = compile_execution_plan(_buffers())

    assert first.plan_hash == second.plan_hash
    assert first.to_dict() == second.to_dict()
    assert first.plan_id == second.plan_id
    for descriptor in first.descriptors:
        array = first.array(descriptor.name)
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_execution_plan_compiles_node_major_dof_partition() -> None:
    plan = compile_execution_plan(_buffers())

    np.testing.assert_array_equal(
        plan.array("node_dof_indices"),
        np.arange(12, dtype="<i4").reshape(2, 6),
    )
    np.testing.assert_array_equal(plan.array("constrained_dofs"), np.arange(6))
    np.testing.assert_array_equal(plan.array("free_dofs"), np.arange(6, 12))
    np.testing.assert_array_equal(
        plan.array("global_to_free"),
        np.asarray([-1, -1, -1, -1, -1, -1, 0, 1, 2, 3, 4, 5]),
    )
    np.testing.assert_array_equal(
        plan.array("element_global_dofs"), np.arange(12).reshape(1, 12)
    )


def test_execution_plan_csr_pattern_is_sorted_symmetric_and_scatter_exact() -> None:
    plan = compile_execution_plan(_buffers())
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    diagonal = plan.array("csr_diagonal_positions")
    scatter = plan.array("csr_element_scatter_indices")

    assert row_ptr.tolist() == [12 * index for index in range(13)]
    assert columns.size == 144
    for row in range(plan.dof_count):
        row_columns = columns[row_ptr[row] : row_ptr[row + 1]]
        assert row_columns.tolist() == list(range(12))
        assert columns[diagonal[row]] == row
        for column in row_columns:
            reverse_start = int(row_ptr[int(column)])
            reverse_stop = int(row_ptr[int(column) + 1])
            assert row in columns[reverse_start:reverse_stop]
    for local_row in range(12):
        for local_column in range(12):
            position = int(scatter[0, local_row, local_column])
            assert position == int(row_ptr[local_row]) + local_column


def test_execution_plan_reduced_csr_maps_back_to_full_value_positions() -> None:
    plan = compile_execution_plan(_buffers())
    reduced_row_ptr = plan.array("reduced_csr_row_ptr")
    reduced_columns = plan.array("reduced_csr_column_indices")
    global_positions = plan.array("reduced_csr_global_value_indices")
    full_columns = plan.array("csr_column_indices")
    global_to_free = plan.array("global_to_free")

    assert reduced_row_ptr.tolist() == [6 * index for index in range(7)]
    for reduced_row in range(6):
        start = int(reduced_row_ptr[reduced_row])
        stop = int(reduced_row_ptr[reduced_row + 1])
        assert reduced_columns[start:stop].tolist() == list(range(6))
        for offset in range(start, stop):
            assert global_to_free[full_columns[global_positions[offset]]] == reduced_columns[
                offset
            ]


def test_execution_plan_compiled_k_f_and_recovery_bind_the_cpu_operator() -> None:
    plan = compile_execution_plan(_buffers())
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    values = plan.array("global_stiffness_csr_values")
    dense = plan.array("global_stiffness_dense")

    for row in range(plan.dof_count):
        start, stop = int(row_ptr[row]), int(row_ptr[row + 1])
        np.testing.assert_array_equal(values[start:stop], dense[row, columns[start:stop]])
    np.testing.assert_array_equal(plan.array("global_load"), plan.operator.load_vector)
    assert plan.recovery_operator_hash == compute_recovery_operator_hash(
        plan.operator, plan.element_ids
    )


def test_backend_and_tolerance_change_plan_receipt_but_not_symbolic_pattern() -> None:
    buffers = _buffers()
    dense = compile_execution_plan(buffers, matrix_backend="dense")
    sparse = compile_execution_plan(buffers, matrix_backend="scipy_sparse")
    loose = compile_execution_plan(
        buffers, matrix_backend="dense", residual_tolerance=1.0e-8
    )

    assert dense.pattern_hash == sparse.pattern_hash == loose.pattern_hash
    assert dense.partition_hash == sparse.partition_hash == loose.partition_hash
    assert len({dense.plan_hash, sparse.plan_hash, loose.plan_hash}) == 3
    assert dense.to_dict()["solver_policy"]["linear_solver"] == "dense_direct"
    assert sparse.to_dict()["solver_policy"]["linear_solver"] == (
        "scipy_sparse_direct"
    )


def test_execution_plan_rejects_stale_array_descriptor_after_byte_tamper() -> None:
    plan = compile_execution_plan(_buffers())
    arrays = dict(plan._arrays)
    forged = np.asarray(arrays["global_load"]).copy()
    forged[-1] += 1.0
    arrays["global_load"] = immutable_array(forged, dtype="<f8")
    tampered = replace(plan, _arrays=MappingProxyType(arrays))

    with pytest.raises(ExecutionPlanError) as error:
        validate_execution_plan(tampered)
    assert error.value.code == "execution_plan_array_descriptor_mismatch"


def test_execution_plan_rejects_rehashed_recovery_operator_tamper() -> None:
    plan = compile_execution_plan(_buffers())
    arrays = dict(plan._arrays)
    forged = np.asarray(arrays["recovery_stiffness_local"]).copy()
    forged[0, 0, 0] += 1.0
    arrays["recovery_stiffness_local"] = immutable_array(forged, dtype="<f8")
    descriptors = tuple(
        _array_descriptor(row.name, arrays[row.name])
        if row.name == "recovery_stiffness_local"
        else row
        for row in plan.descriptors
    )
    tampered = replace(
        plan, descriptors=descriptors, _arrays=MappingProxyType(arrays)
    )

    with pytest.raises(ExecutionPlanError) as error:
        validate_execution_plan(tampered)
    assert error.value.code == "execution_plan_recovery_assembly_mismatch"


def test_execution_plan_rejects_partition_and_aggregate_hash_tampering() -> None:
    plan = compile_execution_plan(_buffers())
    with pytest.raises(ExecutionPlanError) as error:
        validate_execution_plan(replace(plan, partition_hash="sha256:" + "1" * 64))
    assert error.value.code == "execution_plan_partition_hash_mismatch"

    with pytest.raises(ExecutionPlanError) as error:
        validate_execution_plan(replace(plan, plan_hash="sha256:" + "2" * 64))
    assert error.value.code == "execution_plan_hash_mismatch"


def test_execution_plan_rejects_different_buffer_binding() -> None:
    plan = compile_execution_plan(_buffers("LC_AXIAL"))

    with pytest.raises(ExecutionPlanError) as error:
        validate_execution_plan(plan, expected_buffers=_buffers("LC_WEAK"))
    assert error.value.code == "execution_plan_buffer_binding_mismatch"
