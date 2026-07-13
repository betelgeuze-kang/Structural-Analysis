from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.backends.cpu_reference.linear_static import (  # noqa: E402
    LinearStaticResult,
    solve_linear_static,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    SolverModelBuffers,
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    has_immutable_bytes_backing,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    ExecutionPlan,
    compile_execution_plan,
)
from structural_analysis.engine_v2.contracts.result_ir import (  # noqa: E402
    ResultIR,
    ResultIRValidationError,
    build_result_ir,
    validate_result_ir_v1,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    StateIR,
    commit_trial_state,
    create_initial_state,
    open_trial_state,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = REPO_ROOT / "src/structural_analysis/schemas/result_ir_v1.schema.json"
TOLERANCE = 1.0e-10


def _pipeline(
    matrix_backend: str = "dense",
) -> tuple[
    SolverModelBuffers,
    ExecutionPlan,
    StateIR,
    StateIR,
    StateIR,
    LinearStaticResult,
    ResultIR,
]:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_WEAK"
    )
    plan = compile_execution_plan(
        buffers,
        matrix_backend=matrix_backend,
        residual_tolerance=TOLERANCE,
    )
    accepted = create_initial_state(plan)
    backend_result = solve_linear_static(
        buffers,
        matrix_backend=matrix_backend,
        residual_tolerance=TOLERANCE,
    )
    trial = open_trial_state(
        accepted,
        backend_result.displacements_si.reshape(-1),
        expected_plan=plan,
    )
    committed = commit_trial_state(
        accepted,
        trial,
        expected_plan=plan,
    )
    receipt = build_result_ir(
        buffers,
        plan,
        trial,
        committed,
        backend_result,
        matrix_backend=matrix_backend,
        requested_residual_tolerance=TOLERANCE,
    )
    return buffers, plan, accepted, trial, committed, backend_result, receipt


def test_result_ir_is_schema_valid_and_binds_every_upstream_artifact() -> None:
    buffers, plan, _, trial, committed, backend_result, receipt = _pipeline()
    payload = receipt.to_dict()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(payload)
    assert payload["capability_profile"] == "phase0_cpu_reference_linear_static"
    assert receipt.input_bindings.model_ir_content_hash == buffers.model_ir_content_hash
    assert receipt.input_bindings.solver_numeric_buffer_hash == buffers.numeric_buffer_hash
    assert receipt.input_bindings.solver_entity_mapping_hash == buffers.entity_mapping_hash
    assert receipt.input_bindings.solver_artifact_hash == buffers.artifact_hash
    assert receipt.input_bindings.execution_plan_hash == plan.plan_hash
    assert receipt.input_bindings.evaluated_trial_state_hash == trial.state_hash
    assert receipt.input_bindings.committed_state_hash == committed.state_hash
    assert receipt.analysis.operator_hash == plan.operator_hash
    assert receipt.analysis.recovery_operator_hash == plan.recovery_operator_hash
    assert receipt.analysis.backend_native_result_hash == backend_result.result_hash
    assert receipt.result_ir_hash != backend_result.result_hash
    assert payload["backend_receipt"]["timing"]["measurement_status"] == (
        "not_instrumented"
    )
    assert payload["backend_receipt"]["timing"]["total_wall_time_s"] is None
    assert payload["backend_receipt"]["peak_memory"] == {
        "measurement_status": "not_instrumented",
        "peak_host_bytes": None,
        "peak_device_bytes": 0,
    }


def test_result_ir_schema_rejects_cross_labeled_or_non_numeric_array_values() -> None:
    *_, receipt = _pipeline()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    cross_labeled = receipt.to_dict()
    cross_labeled["arrays"]["displacements_si"]["name"] = "residual_si"
    non_numeric = receipt.to_dict()
    non_numeric["arrays"]["reactions_si"]["values"][0][0] = "not-a-number"

    assert not validator.is_valid(cross_labeled)
    assert not validator.is_valid(non_numeric)


def test_result_ir_arrays_are_canonical_immutable_artifacts() -> None:
    *_, receipt = _pipeline()

    for artifact in receipt.arrays.ordered():
        assert artifact.dtype == "<f8"
        assert artifact.byte_length == artifact.values.size * 8
        assert artifact.values.flags.c_contiguous
        assert has_immutable_bytes_backing(artifact.values)
        with pytest.raises(ValueError):
            artifact.values.setflags(write=True)


def test_dense_and_sparse_receipts_are_distinct_and_numerically_equivalent() -> None:
    *_, dense = _pipeline("dense")
    *_, sparse = _pipeline("scipy_sparse")

    assert dense.backend_receipt.matrix_backend == "dense"
    assert sparse.backend_receipt.matrix_backend == "scipy_sparse"
    assert dense.result_ir_hash != sparse.result_ir_hash
    assert dense.analysis.backend_native_result_hash != (
        sparse.analysis.backend_native_result_hash
    )
    for dense_artifact, sparse_artifact in zip(
        dense.arrays.ordered(), sparse.arrays.ordered(), strict=True
    ):
        np.testing.assert_allclose(
            dense_artifact.values,
            sparse_artifact.values,
            rtol=1.0e-12,
            atol=1.0e-12,
        )


def test_result_ir_recomputes_residual_instead_of_trusting_backend_native_hash() -> None:
    buffers, plan, _, trial, committed, backend_result, _ = _pipeline()
    forged_residual = np.array(backend_result.residual_si, copy=True)
    forged_residual[0, 0] += 100.0
    forged_result = replace(backend_result, residual_si=forged_residual)

    with pytest.raises(ResultIRValidationError) as error:
        build_result_ir(
            buffers,
            plan,
            trial,
            committed,
            forged_result,
            matrix_backend="dense",
            requested_residual_tolerance=TOLERANCE,
        )
    assert error.value.code == "result_ir_residual_invariant_failed"


def test_result_ir_recomputes_reactions_and_rejects_free_dof_values() -> None:
    buffers, plan, _, trial, committed, backend_result, _ = _pipeline()
    forged_reactions = np.array(backend_result.reactions_si, copy=True)
    free_dof = backend_result.free_dofs[0]
    forged_reactions.reshape(-1)[free_dof] = 1.0
    forged_result = replace(backend_result, reactions_si=forged_reactions)

    with pytest.raises(ResultIRValidationError) as error:
        build_result_ir(
            buffers,
            plan,
            trial,
            committed,
            forged_result,
            matrix_backend="dense",
            requested_residual_tolerance=TOLERANCE,
        )
    assert error.value.code == "result_ir_reaction_invariant_failed"


def test_result_ir_recomputes_element_global_and_external_work_energy() -> None:
    buffers, plan, _, trial, committed, backend_result, _ = _pipeline()
    forged_result = replace(
        backend_result,
        total_strain_energy_j=backend_result.total_strain_energy_j + 1.0,
    )

    with pytest.raises(ResultIRValidationError) as error:
        build_result_ir(
            buffers,
            plan,
            trial,
            committed,
            forged_result,
            matrix_backend="dense",
            requested_residual_tolerance=TOLERANCE,
        )
    assert error.value.code == "result_ir_total_energy_sum_mismatch"


def test_result_ir_requires_trial_and_commit_displacement_to_equal_result() -> None:
    buffers, plan, accepted, _, _, backend_result, _ = _pipeline()
    different_displacement = np.array(backend_result.displacements_si, copy=True)
    different_displacement.reshape(-1)[backend_result.free_dofs[0]] += 1.0e-4
    trial = open_trial_state(
        accepted,
        different_displacement.reshape(-1),
        expected_plan=plan,
    )
    committed = commit_trial_state(
        accepted,
        trial,
        expected_plan=plan,
    )

    with pytest.raises(ResultIRValidationError) as error:
        build_result_ir(
            buffers,
            plan,
            trial,
            committed,
            backend_result,
            matrix_backend="dense",
            requested_residual_tolerance=TOLERANCE,
        )
    assert error.value.code == "result_ir_trial_state_displacement_mismatch"


def test_result_ir_rejects_backend_operator_hash_from_another_operator() -> None:
    buffers, plan, _, trial, committed, backend_result, _ = _pipeline()
    forged_result = replace(
        backend_result,
        operator_hash="sha256:" + "0" * 64,
    )

    with pytest.raises(ResultIRValidationError) as error:
        build_result_ir(
            buffers,
            plan,
            trial,
            committed,
            forged_result,
            matrix_backend="dense",
            requested_residual_tolerance=TOLERANCE,
        )
    assert error.value.code == "result_ir_operator_hash_mismatch"


def test_result_ir_aggregate_hash_rejects_receipt_metadata_tampering() -> None:
    buffers, plan, _, trial, committed, backend_result, receipt = _pipeline()
    forged = replace(receipt, result_ir_hash="sha256:" + "0" * 64)

    with pytest.raises(ResultIRValidationError) as error:
        validate_result_ir_v1(
            forged,
            buffers=buffers,
            plan=plan,
            evaluated_trial_state=trial,
            committed_state=committed,
            backend_result=backend_result,
        )
    assert error.value.code == "result_ir_aggregate_hash_mismatch"


def test_result_ir_tolerance_is_bound_to_execution_plan() -> None:
    buffers, plan, _, trial, committed, backend_result, _ = _pipeline()

    with pytest.raises(ResultIRValidationError) as error:
        build_result_ir(
            buffers,
            plan,
            trial,
            committed,
            backend_result,
            matrix_backend="dense",
            requested_residual_tolerance=TOLERANCE * 10.0,
        )
    assert error.value.code == "result_ir_tolerance_binding_mismatch"
