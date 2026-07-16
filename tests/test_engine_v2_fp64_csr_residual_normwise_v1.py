from __future__ import annotations

import ast
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
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_model_case_terminal_metric_parity_v2 as terminal_contract,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_parity_v1 import (
    HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_terminal_outcome_observation_v1 import (
    HipFgmresTerminalOutcomeCountersV1,
    HipFgmresTerminalOutcomeMetricsV1,
    HipFgmresTerminalOutcomeV1,
)
from structural_analysis.engine_v2.contracts import (
    fp64_csr_residual_normwise_v1 as normwise,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.engine_v2.solvers.cpu_fgmres import (
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)
from structural_analysis.engine_v2.solvers.gpu_tree_reference_v2 import (
    fgmres_gpu_tree_l2_v2,
    fgmres_gpu_tree_linf_v2,
)

from tests.test_engine_v2_fp64_csr_residual_roundoff_v1 import (
    _bound_for,
    _plan,
    _within_bound_case,
)


ROOT = Path(__file__).resolve().parents[1]
NORMWISE_SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "fp64_csr_residual_normwise_v1.schema.json"
)
TERMINAL_SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_terminal_metric_parity_v2.schema.json"
)
LEGACY_SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas"
    / "hip_fgmres_model_case_parity_v1.schema.json"
)
_ZERO_HASH = "sha256:" + "0" * 64


def _projection(load_scale: float = 10000.0) -> Any:
    return normwise.attest_fp64_csr_residual_normwise_v1(
        _within_bound_case(load_scale)[3]
    )


def _terminal_case(
    load_scale: float = 10000.0,
    *,
    perturbation_fraction: float = 0.125,
) -> tuple[Any, Any, bytes, bytes, HipFgmresTerminalOutcomeV1, int]:
    plan = _plan(load_scale)
    policy = compile_fgmres_policy_v1(
        restart_dimension=8,
        max_iterations=64,
        relative_tolerance=1.0e-10,
    )
    cpu = solve_cpu_fgmres_reference_v1(plan, policy)
    assert cpu.status == "converged"
    initial = _bound_for(
        plan,
        cpu.reduced_solution,
        cpu.reduced_solution,
        cpu.true_residual,
        cpu.true_residual,
    )
    row = int(np.argmax(initial.componentwise))
    candidate = cpu.true_residual.copy()
    candidate[row] += perturbation_fraction * float(initial.componentwise[row])
    candidate[candidate == 0.0] = 0.0
    candidate = np.ascontiguousarray(candidate, dtype="<f8")
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    rhs = plan.array("global_load")[free]
    candidate_l2 = fgmres_gpu_tree_l2_v2(candidate).value
    candidate_linf = fgmres_gpu_tree_linf_v2(candidate).value
    rhs_l2 = fgmres_gpu_tree_l2_v2(rhs).value
    rhs_linf = fgmres_gpu_tree_linf_v2(rhs).value
    candidate_scaled = candidate_linf / max(1.0, rhs_linf)
    solution_l2 = fgmres_gpu_tree_l2_v2(cpu.reduced_solution).value
    metrics = HipFgmresTerminalOutcomeMetricsV1(
        rhs_l2=rhs_l2,
        rhs_linf=rhs_linf,
        solver_tolerance_l2=cpu.solver_tolerance_l2,
        authoritative_tolerance_scaled_linf=plan.residual_tolerance,
        initial_residual_l2=cpu.initial_residual_l2,
        final_residual_l2=candidate_l2,
        final_residual_linf=candidate_linf,
        final_scaled_residual=candidate_scaled,
        previous_checkpoint_residual_l2=candidate_l2,
        solution_update_l2=0.0,
        solution_scale_l2=solution_l2,
        estimated_residual_l2=candidate_l2,
        arnoldi_work_l2=0.0,
        arnoldi_breakdown_threshold=0.0,
        triangular_scale=0.0,
    )
    counters = HipFgmresTerminalOutcomeCountersV1(
        scheduled_iterations=cpu.iteration_count,
        effective_iterations=cpu.iteration_count,
        scheduled_restarts=cpu.restart_count,
        effective_restarts=cpu.restart_count,
        effective_arnoldi_dimension=policy.restart_dimension,
        happy_breakdown_count=0,
        stagnation_checkpoint_count=0,
        false_convergence_count=0,
        operator_apply_count=cpu.operator_apply_count,
        preconditioner_apply_count=cpu.preconditioner_apply_count,
        restart_dimension=policy.restart_dimension,
    )
    outcome = HipFgmresTerminalOutcomeV1(
        outcome_class="converged",
        active=0,
        terminal_status=cpu.status,
        terminal_status_code=1,
        termination_code=cpu.termination_code,
        termination_code_value=2,
        device_error_bits=0,
        device_error_names=(),
        counters=counters,
        record_metrics_authoritative=True,
        metrics=metrics,
        restart_rows=(),
        solution_x_all_finite=True,
        true_residual_all_finite=True,
        observed_solution_x_l2=solution_l2,
        observed_true_residual_l2=candidate_l2,
        observed_true_residual_linf=candidate_linf,
        observed_true_residual_scaled_linf=candidate_scaled,
        true_residual_record_metrics_match=True,
    )
    return (
        plan,
        cpu,
        cpu.reduced_solution.tobytes(order="C"),
        candidate.tobytes(order="C"),
        outcome,
        row,
    )


def _terminal_result(**kwargs: Any) -> Any:
    plan, cpu, solution_x, residual, outcome, _row = _terminal_case(**kwargs)
    return terminal_contract.replay_hip_fgmres_detached_terminal_metric_parity_v2(
        execution_plan=plan,
        cpu_result=cpu,
        solution_x=solution_x,
        true_residual=residual,
        outcome=outcome,
    )


def _rehash_normwise(receipt: Any, **changes: Any) -> Any:
    draft = replace(receipt, **changes, receipt_hash=_ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            normwise._receipt_payload(draft, include_hash=False)
        ),
    )


def _rehash_terminal(receipt: Any, **changes: Any) -> Any:
    draft = replace(receipt, **changes, receipt_hash=_ZERO_HASH)
    return replace(
        draft,
        receipt_hash=canonical_hash(
            terminal_contract._receipt_payload(draft, include_hash=False)
        ),
    )


def test_normwise_projection_has_strict_three_metric_contract() -> None:
    result = _projection()
    receipt = result.receipt

    assert tuple(row.name for row in receipt.metrics) == (
        "l2",
        "linf",
        "scaled_linf",
    )
    assert receipt.summary.metric_count == 3
    assert receipt.summary.load_scale == 10000.0
    assert receipt.compatibility.migration_action == (
        "preserve_v1_and_issue_additive_normwise_v1"
    )
    assert not receipt.compatibility.source_wire_receipt_mutated
    assert not receipt.claims.actual_backend_verified
    assert not receipt.claims.terminal_record_metric_verified
    assert not receipt.claims.history_metric_verified
    assert normwise.validate_fp64_csr_residual_normwise_result_v1(result) is result
    Draft202012Validator(
        json.loads(NORMWISE_SCHEMA.read_text(encoding="utf-8"))
    ).validate(receipt.to_dict())


def test_l2_outward_intervals_enclose_exact_fraction_sum_of_squares() -> None:
    result = _projection()
    source = result._componentwise_result
    l2 = result.receipt.metrics[0]
    for vector, interval in (
        (source._reference_residual, l2.reference_interval),
        (source._candidate_residual, l2.candidate_interval),
    ):
        exact_square = sum(
            (Fraction.from_float(float(value)) ** 2 for value in vector),
            start=Fraction(0),
        )
        assert Fraction.from_float(interval.lower) ** 2 <= exact_square
        assert exact_square <= Fraction.from_float(interval.upper) ** 2


def test_power_of_two_scaling_projects_raw_and_scaled_metric_budgets() -> None:
    unit = _projection(1.0).receipt
    large = _projection(2.0**20).receipt
    small = _projection(2.0**-20).receipt

    assert large.metrics[0].vector_difference_upper_bound == pytest.approx(
        unit.metrics[0].vector_difference_upper_bound * 2.0**20,
        rel=4.0e-15,
    )
    assert large.metrics[1].vector_difference_upper_bound == pytest.approx(
        unit.metrics[1].vector_difference_upper_bound * 2.0**20,
        rel=4.0e-15,
    )
    assert large.metrics[2].vector_difference_upper_bound == pytest.approx(
        unit.metrics[2].vector_difference_upper_bound,
        rel=4.0e-15,
    )
    assert small.summary.load_scale == 1.0
    assert small.metrics[2].vector_difference_upper_bound == pytest.approx(
        small.metrics[1].vector_difference_upper_bound,
        rel=4.0e-15,
    )


def test_exact_equal_vectors_have_zero_interval_gap_and_valid_budget() -> None:
    plan, solution, residual, _source = _within_bound_case(1.0)
    from structural_analysis.engine_v2.contracts.fp64_csr_residual_roundoff_v1 import (
        attest_fp64_csr_residual_roundoff_v1,
    )

    componentwise = attest_fp64_csr_residual_roundoff_v1(
        plan,
        solution,
        solution.copy(),
        residual,
        residual.copy(),
    )
    projected = normwise.attest_fp64_csr_residual_normwise_v1(componentwise)
    assert all(row.interval_gap_lower_bound == 0.0 for row in projected.receipt.metrics)
    assert all(row.reverse_triangle_bound_verified for row in projected.receipt.metrics)


def test_normwise_receipt_and_result_reject_coherent_relabel_or_source_splice() -> None:
    first = _projection(1.0)
    second = _projection(2.0)
    forged = _rehash_normwise(
        first.receipt,
        bindings=replace(
            first.receipt.bindings,
            componentwise_receipt_hash=second.receipt.bindings.componentwise_receipt_hash,
        ),
    )
    with pytest.raises(normwise.Fp64CsrResidualNormwiseV1Error):
        normwise.validate_fp64_csr_residual_normwise_receipt_v1(forged)
    with pytest.raises(normwise.Fp64CsrResidualNormwiseV1Error) as caught:
        normwise.validate_fp64_csr_residual_normwise_result_v1(
            first,
            expected_componentwise_result=second._componentwise_result,
        )
    assert caught.value.code == "fp64_csr_residual_normwise_source_identity_mismatch"


def test_terminal_v2_binds_verified_cpu_and_gpu_tree_records_without_tolerance() -> (
    None
):
    result = _terminal_result(perturbation_fraction=0.125)
    receipt = result.receipt

    assert tuple(row.name for row in receipt.records) == (
        "l2",
        "linf",
        "scaled_linf",
    )
    assert all(row.record_difference_bound_passed for row in receipt.records)
    assert any(
        row.absolute_record_difference_upper_bound > 0.0 for row in receipt.records
    )
    assert receipt.summary.maximum_record_bound_ratio <= 1.0
    assert receipt.compatibility.migration_action == (
        "preserve_v1_and_issue_additive_terminal_metric_v2"
    )
    assert not receipt.compatibility.legacy_terminal_or_history_gate_relaxed
    assert not receipt.claims.actual_backend_verified
    assert not receipt.claims.history_metric_v2_verified
    assert (
        terminal_contract.validate_hip_fgmres_terminal_metric_parity_result_v2(result)
        is result
    )
    Draft202012Validator(
        json.loads(TERMINAL_SCHEMA.read_text(encoding="utf-8"))
    ).validate(receipt.to_dict())


def test_terminal_v2_accepts_difference_above_legacy_absolute_floor() -> None:
    result = _terminal_result(perturbation_fraction=0.25)
    assert any(
        row.absolute_record_difference_upper_bound
        > HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1
        for row in result.receipt.records[:2]
    )
    assert all(row.maximum_bound_ratio <= 1.0 for row in result.receipt.records)


def test_terminal_v2_rejects_candidate_gpu_tree_record_relabel() -> None:
    plan, cpu, solution, residual, outcome, _row = _terminal_case()
    assert outcome.metrics is not None
    forged_metrics = replace(
        outcome.metrics,
        final_residual_l2=math.nextafter(outcome.metrics.final_residual_l2, math.inf),
    )
    forged = replace(outcome, metrics=forged_metrics)
    with pytest.raises(
        terminal_contract.HipFgmresTerminalMetricParityV2Error
    ) as caught:
        terminal_contract.replay_hip_fgmres_detached_terminal_metric_parity_v2(
            execution_plan=plan,
            cpu_result=cpu,
            solution_x=solution,
            true_residual=residual,
            outcome=forged,
        )
    assert caught.value.code == "hip_fgmres_terminal_metric_candidate_record_mismatch"


def test_terminal_result_rejects_coherent_receipt_rehash() -> None:
    result = _terminal_result()
    first = result.receipt.records[0]
    forged_row = replace(first, maximum_bound_ratio=0.0)
    projection_hash = canonical_hash(
        [
            forged_row.to_dict(),
            *[row.to_dict() for row in result.receipt.records[1:]],
        ]
    )
    forged_bindings = replace(
        result.receipt.bindings,
        terminal_metric_projection_hash=projection_hash,
    )
    forged = _rehash_terminal(
        result.receipt,
        records=(forged_row, *result.receipt.records[1:]),
        bindings=forged_bindings,
        parity_id=canonical_hash(
            {
                "profile": terminal_contract.HIP_FGMRES_TERMINAL_METRIC_PARITY_CAPABILITY_PROFILE_V2,
                "cpu_candidate_normwise_receipt_hash": (
                    forged_bindings.cpu_candidate_normwise_receipt_hash
                ),
                "terminal_outcome_hash": forged_bindings.terminal_outcome_hash,
                "terminal_metric_projection_hash": projection_hash,
            }
        ),
    )
    direct = replace(result, receipt=forged)
    with pytest.raises(
        terminal_contract.HipFgmresTerminalMetricParityV2Error
    ) as caught:
        terminal_contract.validate_hip_fgmres_terminal_metric_parity_result_v2(direct)
    assert caught.value.code == "hip_fgmres_terminal_metric_replay_mismatch"


def test_terminal_result_rejects_forged_legacy_solution_child() -> None:
    result = _terminal_result()
    forged_solution = replace(
        result.roundoff_replay.solution_comparison,
        maximum_tolerance_ratio=0.5,
    )
    forged_roundoff = replace(
        result.roundoff_replay,
        solution_comparison=forged_solution,
    )
    forged = replace(result, roundoff_replay=forged_roundoff)
    with pytest.raises(
        terminal_contract.HipFgmresTerminalMetricParityV2Error
    ) as caught:
        terminal_contract.validate_hip_fgmres_terminal_metric_parity_result_v2(forged)
    assert caught.value.code == "hip_fgmres_terminal_metric_child_replay_mismatch"


def test_v1_wire_schema_and_fixed_gate_constants_remain_frozen() -> None:
    assert hashlib.sha256(LEGACY_SCHEMA.read_bytes()).hexdigest() == (
        "4da38578a99ba1c479f32b66f62ef8c1771b4e734f947c1a0b24e1648066f050"
    )
    assert engine_v2.HIP_FGMRES_MODEL_CASE_PARITY_ABSOLUTE_TOLERANCE_V1 == 1.0e-12
    assert engine_v2.HIP_FGMRES_MODEL_CASE_PARITY_RELATIVE_TOLERANCE_V1 == 1.0e-8


def test_public_exports_are_identity_preserving() -> None:
    contract_names = (
        "Fp64CsrResidualNormwiseResultV1",
        "attest_fp64_csr_residual_normwise_v1",
        "validate_fp64_csr_residual_normwise_result_v1",
    )
    for name in contract_names:
        value = getattr(normwise, name)
        assert getattr(contracts, name) is value
        assert getattr(engine_v2, name) is value
        assert name in contracts.__all__
        assert name in engine_v2.__all__
    assembly_names = (
        "HipFgmresTerminalMetricParityResultV2",
        "replay_hip_fgmres_detached_terminal_metric_parity_v2",
        "validate_hip_fgmres_terminal_metric_parity_result_v2",
    )
    for name in assembly_names:
        value = getattr(terminal_contract, name)
        assert getattr(assembly_backend, name) is value
        assert getattr(engine_v2, name) is value
        assert name in assembly_backend.__all__
        assert name in engine_v2.__all__


def test_new_modules_and_schemas_are_packaged_byte_identically(tmp_path: Path) -> None:
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
        "structural_analysis/engine_v2/contracts/fp64_csr_residual_normwise_v1.py": (
            Path(inspect.getsourcefile(normwise) or "")
        ),
        "structural_analysis/engine_v2/assembly_backend/fgmres_model_case_terminal_metric_parity_v2.py": (
            Path(inspect.getsourcefile(terminal_contract) or "")
        ),
        "structural_analysis/schemas/fp64_csr_residual_normwise_v1.schema.json": (
            NORMWISE_SCHEMA
        ),
        "structural_analysis/schemas/hip_fgmres_terminal_metric_parity_v2.schema.json": (
            TERMINAL_SCHEMA
        ),
    }
    with ZipFile(wheels[0]) as archive:
        assert expected.keys() <= set(archive.namelist())
        for archive_path, source_path in expected.items():
            assert archive.read(archive_path) == source_path.read_bytes()


def test_contracts_have_no_tolerance_dense_or_solve_surface() -> None:
    assert (
        "tolerance"
        not in inspect.signature(
            normwise.attest_fp64_csr_residual_normwise_v1
        ).parameters
    )
    assert (
        "tolerance"
        not in inspect.signature(
            terminal_contract.replay_hip_fgmres_detached_terminal_metric_parity_v2
        ).parameters
    )
    for module in (normwise, terminal_contract):
        tree = ast.parse(Path(inspect.getsourcefile(module) or "").read_text())
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not {"solve", "inv", "pinv", "lstsq", "dot", "matmul"} & calls
        source = inspect.getsource(module)
        assert "scipy" not in source.lower()
        assert "np.zeros((" not in source
