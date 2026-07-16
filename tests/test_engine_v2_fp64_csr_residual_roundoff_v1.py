from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import hashlib
import inspect
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any
from zipfile import ZipFile

from jsonschema import Draft202012Validator
import numpy as np
import pytest

import structural_analysis.engine_v2 as engine_v2
import structural_analysis.engine_v2.assembly_backend as assembly_backend
import structural_analysis.engine_v2.contracts as contracts
from structural_analysis.engine_v2 import pack_solver_model_buffers
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_case_parity_v1 as parity_module,
)
from structural_analysis.engine_v2.contracts import (
    fp64_csr_residual_roundoff_v1 as contract,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (
    ExecutionPlanV2,
    compile_execution_plan_v2,
)
from structural_analysis.model_ir import parse_model_ir_v2
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_all_converged_v1"
    / "solution_frame_single_rotated_axis_bending.model.json"
)
SCHEMA_PATH = (
    ROOT
    / "src/structural_analysis/schemas"
    / "fp64_csr_residual_roundoff_v1.schema.json"
)
_ZERO_HASH = "sha256:" + "0" * 64


def _plan(load_scale: float = 1.0) -> ExecutionPlanV2:
    payload = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    payload["load_patterns"][0]["nodal_loads"][0]["components_si"]["FY"] = -load_scale
    source_ref = f"test:fp64-csr-residual-roundoff:{float.hex(load_scale)}"
    payload["provenance"] = deepcopy(payload["provenance"])
    payload["provenance"]["source_ref"] = source_ref
    payload["provenance"]["source_sha256"] = (
        "sha256:" + hashlib.sha256(source_ref.encode("utf-8")).hexdigest()
    )
    model = parse_model_ir_v2(payload, require_analysis_ready=True)
    return compile_execution_plan_v2(
        pack_solver_model_buffers(model, load_pattern_id="LC_WEAK"),
        residual_tolerance=1.0e-8,
    )


def _dense_solution(plan: ExecutionPlanV2) -> np.ndarray:
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    size = row_ptr.size - 1
    matrix = np.zeros((size, size), dtype="<f8")
    for row in range(size):
        start, stop = int(row_ptr[row]), int(row_ptr[row + 1])
        matrix[row, columns[start:stop]] = values[start:stop]
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    solution = np.ascontiguousarray(
        np.linalg.solve(matrix, plan.array("global_load")[free]),
        dtype="<f8",
    )
    solution[solution == 0.0] = 0.0
    return solution


def _residual(plan: ExecutionPlanV2, solution: np.ndarray) -> np.ndarray:
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    rhs = plan.array("global_load")[free]
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    residual = np.empty(free.size, dtype="<f8")
    for row in range(free.size):
        start, stop = int(row_ptr[row]), int(row_ptr[row + 1])
        product = math.fsum(
            float(values[index]) * float(solution[int(columns[index])])
            for index in range(start, stop)
        )
        residual[row] = float(rhs[row]) - product
    residual[residual == 0.0] = 0.0
    return residual


def _bound_for(
    plan: ExecutionPlanV2,
    reference_solution: np.ndarray,
    candidate_solution: np.ndarray,
    reference_residual: np.ndarray,
    candidate_residual: np.ndarray,
) -> Any:
    return contract._compute_bounds(
        plan,
        reference_solution,
        candidate_solution,
        reference_residual,
        candidate_residual,
    )


def _within_bound_case(
    load_scale: float = 1.0,
) -> tuple[ExecutionPlanV2, np.ndarray, np.ndarray, Any]:
    plan = _plan(load_scale)
    solution = _dense_solution(plan)
    reference = _residual(plan, solution)
    initial = _bound_for(plan, solution, solution, reference, reference)
    row = int(np.argmax(initial.componentwise))
    candidate = reference.copy()
    candidate[row] += 0.25 * float(initial.componentwise[row])
    candidate[candidate == 0.0] = 0.0
    result = contract.attest_fp64_csr_residual_roundoff_v1(
        plan,
        solution,
        solution.copy(),
        reference,
        candidate,
    )
    return plan, solution, reference, result


def _rehash(
    receipt: contract.Fp64CsrResidualRoundoffReceiptV1,
    **changes: Any,
) -> contract.Fp64CsrResidualRoundoffReceiptV1:
    draft = replace(receipt, **changes, receipt_hash=_ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            contract._receipt_payload(draft, include_hash=False)
        ),
    )


def test_schema_receipt_and_claim_boundary_are_strict() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    plan, _solution, _reference, result = _within_bound_case()
    receipt = result.receipt

    assert contract.validate_fp64_csr_residual_roundoff_receipt_v1(receipt) is receipt
    assert (
        contract.validate_fp64_csr_residual_roundoff_result_v1(
            result,
            expected_execution_plan=plan,
        )
        is result
    )
    assert not list(Draft202012Validator(schema).iter_errors(receipt.to_dict()))
    assert receipt.arithmetic_model.binary64_unit_roundoff == 2.0**-53
    assert receipt.arithmetic_model.binary64_smallest_subnormal == float.fromhex(
        "0x0.0000000000001p-1022"
    )
    assert not receipt.arithmetic_model.caller_tolerance_allowed
    assert receipt.claims.no_user_absolute_tolerance_floor
    assert receipt.claims.sparse_o_nnz_plus_n_work_bound
    assert not receipt.claims.actual_backend_verified
    assert not receipt.claims.hardware_provenance_verified
    assert not receipt.claims.end_to_end_o_n_verified
    assert not receipt.claims.commercial_ready
    assert not receipt.promotion_eligible


def test_public_names_are_identity_exported_from_contracts_and_engine() -> None:
    for name in contract.__all__:
        value = getattr(contract, name)
        assert getattr(contracts, name) is value
        assert getattr(engine_v2, name) is value
        assert name in contracts.__all__
        assert name in engine_v2.__all__
    for name in (
        "HipFgmresDetachedResidualRoundoffReplayV1",
        "replay_hip_fgmres_detached_residual_roundoff_v1",
    ):
        value = getattr(parity_module, name)
        assert getattr(assembly_backend, name) is value
        assert getattr(engine_v2, name) is value
        assert name in assembly_backend.__all__
        assert name in engine_v2.__all__


def test_contract_module_and_schema_are_packaged_in_actual_wheel(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(tmp_path),
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    wheels = tuple(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    expected = {
        "structural_analysis/engine_v2/contracts/fp64_csr_residual_roundoff_v1.py": (
            ROOT
            / "src/structural_analysis/engine_v2/contracts"
            / "fp64_csr_residual_roundoff_v1.py"
        ),
        "structural_analysis/schemas/fp64_csr_residual_roundoff_v1.schema.json": (
            SCHEMA_PATH
        ),
    }
    with ZipFile(wheels[0]) as archive:
        assert expected.keys() <= set(archive.namelist())
        for archive_path, source_path in expected.items():
            assert archive.read(archive_path) == source_path.read_bytes()


def test_near_zero_cancellation_difference_uses_physical_roundoff_scale() -> None:
    _plan_value, _solution, reference, result = _within_bound_case(10000.0)
    summary = result.receipt.summary

    assert np.max(np.abs(reference)) < 1.0e-8
    assert summary.componentwise_bound_passed
    assert 0.0 < summary.maximum_componentwise_bound_ratio < 0.5
    assert summary.maximum_solution_transport_bound == 0.0
    assert summary.maximum_reference_roundoff_bound > 1.0e-12
    assert summary.maximum_candidate_roundoff_bound > 1.0e-12
    assert summary.reference_componentwise_backward_error < 1.0e-12
    assert summary.candidate_componentwise_backward_error < 1.0e-12


def test_power_of_two_load_scaling_preserves_bound_and_backward_error_ratios() -> None:
    observations = []
    for scale in (2.0**-20, 1.0, 2.0**20):
        _plan_value, _solution, _reference, result = _within_bound_case(scale)
        observations.append((scale, result.receipt.summary))

    baseline = observations[1][1]
    for scale, summary in observations:
        assert summary.componentwise_bound_linf / baseline.componentwise_bound_linf == (
            pytest.approx(scale, rel=5.0e-13)
        )
        assert summary.maximum_absolute_difference_upper_bound / (
            baseline.maximum_absolute_difference_upper_bound
        ) == pytest.approx(scale, rel=5.0e-13)
        assert summary.maximum_componentwise_bound_ratio == pytest.approx(
            baseline.maximum_componentwise_bound_ratio,
            rel=5.0e-12,
        )
        assert summary.candidate_componentwise_backward_error == pytest.approx(
            baseline.candidate_componentwise_backward_error,
            rel=5.0e-12,
        )


def test_solution_transport_term_covers_exact_operator_change() -> None:
    plan = _plan()
    reference_solution = np.zeros(
        plan.array("free_dofs").size,
        dtype="<f8",
    )
    candidate_solution = reference_solution.copy()
    candidate_solution[0] = 2.0**-30
    reference_residual = _residual(plan, reference_solution)
    candidate_residual = _residual(plan, candidate_solution)

    result = contract.attest_fp64_csr_residual_roundoff_v1(
        plan,
        reference_solution,
        candidate_solution,
        reference_residual,
        candidate_residual,
    )

    assert not result.receipt.summary.same_solution_bytes
    assert result.receipt.summary.maximum_solution_transport_bound > 0.0
    assert result.receipt.summary.componentwise_bound_passed


def test_componentwise_error_above_derived_bound_fails_closed() -> None:
    plan = _plan(10000.0)
    solution = _dense_solution(plan)
    reference = _residual(plan, solution)
    initial = _bound_for(plan, solution, solution, reference, reference)
    row = int(np.argmax(initial.componentwise))
    candidate = reference.copy()
    candidate[row] += 2.0 * float(initial.componentwise[row])

    with pytest.raises(contract.Fp64CsrResidualRoundoffV1Error) as caught:
        contract.attest_fp64_csr_residual_roundoff_v1(
            plan,
            solution,
            solution.copy(),
            reference,
            candidate,
        )
    assert caught.value.code == ("fp64_csr_residual_roundoff_componentwise_mismatch")
    assert caught.value.path == f"/rows/{row}"


def test_detached_fgmres_adapter_adds_roundoff_gate_without_relaxing_legacy_v1() -> (
    None
):
    plan = _plan(10000.0)
    policy = compile_fgmres_policy_v1(
        restart_dimension=6,
        max_iterations=24,
        relative_tolerance=1.0e-10,
    )
    cpu = solve_cpu_fgmres_reference_v1(plan, policy)
    assert cpu.status == "converged"
    solution = cpu.reduced_solution
    reference = cpu.true_residual
    initial = _bound_for(plan, solution, solution, reference, reference)
    row = int(np.argmax(initial.componentwise))
    candidate = reference.copy()
    candidate[row] += 0.25 * float(initial.componentwise[row])
    candidate[candidate == 0.0] = 0.0

    replay = parity_module.replay_hip_fgmres_detached_residual_roundoff_v1(
        execution_plan=plan,
        cpu_result=cpu,
        solution_x=solution.tobytes(order="C"),
        true_residual=candidate.tobytes(order="C"),
    )

    assert replay.solution_comparison.componentwise_tolerance_passed
    assert replay.cpu_reference_vs_candidate.receipt.summary.componentwise_bound_passed
    assert (
        replay.cpu_reference_vs_candidate.receipt.summary.maximum_absolute_difference_upper_bound
        > parity_module.HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
    )
    assert not replay.cpu_reference_vs_candidate.receipt.claims.actual_backend_verified
    with pytest.raises(parity_module.HipFgmresModelCaseParityV1Error) as caught:
        parity_module.replay_hip_fgmres_detached_model_case_numerics_v1(
            execution_plan=plan,
            cpu_result=cpu,
            solution_x=solution.tobytes(order="C"),
            true_residual=candidate.tobytes(order="C"),
            outcome=object(),
        )
    assert caught.value.code == "hip_fgmres_model_case_parity_vector_mismatch"


def test_outward_primitives_bound_exact_binary64_arithmetic() -> None:
    positive_pairs = (
        (0.0, 0.0),
        (float.fromhex("0x0.0000000000001p-1022"), 3.0),
        (float.fromhex("0x1.0000000000000p-1022"), 0.5),
        (1.0, 2.0**-53),
        (1.0e100, 1.0e-100),
        (math.pi, math.e),
    )
    for left, right in positive_pairs:
        addition = contract._add_up(left, right, "/test/add")
        product = contract._mul_up(left, right, "/test/mul")
        assert Fraction.from_float(addition) >= (
            Fraction.from_float(left) + Fraction.from_float(right)
        )
        assert Fraction.from_float(product) >= (
            Fraction.from_float(left) * Fraction.from_float(right)
        )

    signed_pairs = (
        (1.0, -1.0),
        (math.pi, math.e),
        (-1.0e100, -math.nextafter(1.0e100, -math.inf)),
        (float.fromhex("0x0.0000000000001p-1022"), 0.0),
    )
    for left, right in signed_pairs:
        distance = contract._distance_up(left, right, "/test/distance")
        exact = abs(Fraction.from_float(left) - Fraction.from_float(right))
        assert Fraction.from_float(distance) >= exact

    for operation_count in (1, 3, 13, 1025):
        gamma = contract._gamma(operation_count, "/test/gamma")
        exact = (Fraction(operation_count) * Fraction(1, 2**53)) / (
            1 - Fraction(operation_count) * Fraction(1, 2**53)
        )
        assert Fraction.from_float(gamma) >= exact


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.astype(">f8"),
        lambda value: value.astype("<f4"),
        lambda value: np.concatenate((value, np.array([0.0], dtype="<f8"))),
        lambda value: np.full_like(value, np.nan),
        lambda value: np.full_like(value, -0.0),
    ),
    ids=("big_endian", "float32", "wrong_extent", "nonfinite", "signed_zero"),
)
def test_vector_inputs_fail_closed_before_receipt(mutate) -> None:
    plan = _plan()
    solution = _dense_solution(plan)
    residual = _residual(plan, solution)
    invalid = mutate(solution)

    with pytest.raises(contract.Fp64CsrResidualRoundoffV1Error) as caught:
        contract.attest_fp64_csr_residual_roundoff_v1(
            plan,
            invalid,
            solution,
            residual,
            residual.copy(),
        )
    assert caught.value.code == "fp64_csr_residual_roundoff_vector_invalid"


def test_result_snapshots_vectors_and_rejects_plan_identity_substitution() -> None:
    plan, solution, reference, result = _within_bound_case()
    manifest = result.to_manifest()
    solution[:] = 123.0
    reference[:] = 456.0

    assert result.to_manifest() == manifest
    other_plan = _plan(2.0)
    with pytest.raises(contract.Fp64CsrResidualRoundoffV1Error) as caught:
        contract.validate_fp64_csr_residual_roundoff_result_v1(
            result,
            expected_execution_plan=other_plan,
        )
    assert caught.value.code == "fp64_csr_residual_roundoff_plan_identity_mismatch"


@pytest.mark.parametrize(
    ("change", "expected_code"),
    (
        (
            lambda receipt: replace(receipt, receipt_hash=_ZERO_HASH),
            "fp64_csr_residual_roundoff_receipt_hash_invalid",
        ),
        (
            lambda receipt: _rehash(
                receipt,
                arithmetic_model=replace(
                    receipt.arithmetic_model,
                    caller_tolerance_allowed=True,  # type: ignore[arg-type]
                ),
            ),
            "fp64_csr_residual_roundoff_schema_invalid",
        ),
        (
            lambda receipt: _rehash(
                receipt,
                claims=replace(receipt.claims, actual_backend_verified=True),  # type: ignore[arg-type]
            ),
            "fp64_csr_residual_roundoff_schema_invalid",
        ),
        (
            lambda receipt: _rehash(
                receipt,
                summary=replace(
                    receipt.summary,
                    maximum_componentwise_bound_ratio=1.0000000000000002,
                ),
            ),
            "fp64_csr_residual_roundoff_schema_invalid",
        ),
    ),
)
def test_receipt_rejects_stale_or_coherently_rehashed_relaxation(
    change,
    expected_code: str,
) -> None:
    receipt = _within_bound_case()[3].receipt
    with pytest.raises(contract.Fp64CsrResidualRoundoffV1Error) as caught:
        contract.validate_fp64_csr_residual_roundoff_receipt_v1(change(receipt))
    assert caught.value.code == expected_code


def test_contract_source_has_sparse_linear_shape_and_no_backend_claim_path() -> None:
    source = inspect.getsource(contract)
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not any(name.startswith("scipy") for name in imports)
    assert "linalg" not in calls
    assert "solve" not in calls
    assert "dot" not in calls
    assert "matmul" not in calls
    assert "_compute_bounds" in source
    assert "for row in range(row_count)" in source
    assert "for index in range(start, stop)" in source
    assert "actual_backend_verified: Literal[False]" in source
    assert "end_to_end_o_n_verified: Literal[False]" in source
