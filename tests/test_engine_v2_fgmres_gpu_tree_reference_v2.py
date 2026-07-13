from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.solvers.gpu_tree_reference_v2 import (  # noqa: E402
    FGMRES_GPU_TREE_THREADS_PER_BLOCK,
    FGMRES_GPU_TREE_VALUES_PER_BLOCK,
    FgmresGpuTreeFirstColumnCandidatePreparationV2,
    FgmresGpuTreeFirstColumnCandidateResidualReplayV2,
    FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2,
    FgmresGpuTreeFirstColumnCheckpointTransactionRecordV2,
    FgmresGpuTreeFirstColumnCheckpointTransactionReplayV2,
    FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2,
    FgmresGpuTreeReferenceV2Error,
    fgmres_gpu_tree_dot_v2,
    fgmres_gpu_tree_l2_v2,
    fgmres_gpu_tree_linf_v2,
    prepare_fgmres_gpu_tree_first_column_candidate_residual_v2,
    prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2,
    prepare_fgmres_gpu_tree_first_column_candidate_v2,
    prepare_fgmres_gpu_tree_first_column_checkpoint_transaction_v2,
    replay_fgmres_gpu_tree_first_arnoldi_column_v2,
    replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2,
    replay_fgmres_gpu_tree_first_column_candidate_preparation_v2,
    replay_fgmres_gpu_tree_first_column_candidate_residual_v2,
    replay_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2,
    replay_fgmres_gpu_tree_first_column_checkpoint_transaction_v2,
    replay_fgmres_gpu_tree_initial_v2,
)
import structural_analysis.engine_v2 as engine_v2  # noqa: E402
import structural_analysis.engine_v2.solvers as solvers  # noqa: E402


@pytest.mark.parametrize(
    ("count", "stages"),
    (
        (1, (1,)),
        (255, (1,)),
        (256, (1,)),
        (511, (1,)),
        (512, (1,)),
        (513, (2, 1)),
    ),
)
def test_gpu_tree_l2_and_linf_exact_block_boundaries(
    count: int,
    stages: tuple[int, ...],
) -> None:
    values = np.ones(count, dtype="<f8")
    l2 = fgmres_gpu_tree_l2_v2(values)
    linf = fgmres_gpu_tree_linf_v2(values)

    assert FGMRES_GPU_TREE_THREADS_PER_BLOCK == 256
    assert FGMRES_GPU_TREE_VALUES_PER_BLOCK == 512
    assert l2.stage_output_counts == stages
    assert linf.stage_output_counts == stages
    assert l2.value == math.sqrt(float(count))
    assert linf.value == 1.0
    assert l2.value_count == linf.value_count == count


def test_gpu_tree_reference_public_api_is_reexported() -> None:
    names = (
        "FGMRES_GPU_TREE_REFERENCE_V2_VERSION",
        "FGMRES_GPU_TREE_THREADS_PER_BLOCK",
        "FGMRES_GPU_TREE_VALUES_PER_BLOCK",
        "FgmresGpuTreeFirstArnoldiColumnReplayV2",
        "FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2",
        "FgmresGpuTreeFirstColumnCandidatePreparationV2",
        "FgmresGpuTreeInitialReplayV2",
        "FgmresGpuTreeReductionV2",
        "FgmresGpuTreeReferenceV2Error",
        "fgmres_gpu_tree_dot_v2",
        "fgmres_gpu_tree_l2_v2",
        "fgmres_gpu_tree_linf_v2",
        "prepare_fgmres_gpu_tree_first_column_candidate_v2",
        "replay_fgmres_gpu_tree_first_arnoldi_column_v2",
        "replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2",
        "replay_fgmres_gpu_tree_first_column_candidate_preparation_v2",
        "replay_fgmres_gpu_tree_initial_v2",
    )
    for name in names:
        assert name in solvers.__all__
        assert name in engine_v2.__all__
        assert getattr(engine_v2, name) is getattr(solvers, name)

    solver_only_names = (
        "FgmresGpuTreeFirstColumnCandidateResidualReplayV2",
        "FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2",
        "FgmresGpuTreeFirstColumnCheckpointTransactionRecordV2",
        "FgmresGpuTreeFirstColumnCheckpointTransactionReplayV2",
        "prepare_fgmres_gpu_tree_first_column_candidate_residual_v2",
        "prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2",
        "prepare_fgmres_gpu_tree_first_column_checkpoint_transaction_v2",
        "replay_fgmres_gpu_tree_first_column_candidate_residual_v2",
        "replay_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2",
        "replay_fgmres_gpu_tree_first_column_checkpoint_transaction_v2",
    )
    for name in solver_only_names:
        assert name in solvers.__all__
        assert name in engine_v2.__all__
        assert getattr(solvers, name) is globals()[name]
        assert getattr(engine_v2, name) is globals()[name]


def test_gpu_tree_true_multistage_reduction_is_deterministic() -> None:
    count = 512 * 512 + 1
    values = np.ones(count, dtype="<f8")
    first_l2 = fgmres_gpu_tree_l2_v2(values)
    second_l2 = fgmres_gpu_tree_l2_v2(values.copy())
    first_linf = fgmres_gpu_tree_linf_v2(values)

    assert first_l2.stage_output_counts == (513, 2, 1)
    assert first_linf.stage_output_counts == (513, 2, 1)
    assert first_l2 == second_l2
    assert first_l2.value == math.sqrt(float(count))
    assert first_linf.value == 1.0


def test_gpu_tree_moderate_random_values_match_independent_fsum_oracle() -> None:
    generator = np.random.default_rng(20260711)
    for count in (1, 255, 256, 511, 512, 513, 4097):
        values = generator.normal(size=count).astype("<f8")
        tree_l2 = fgmres_gpu_tree_l2_v2(values).value
        tree_linf = fgmres_gpu_tree_linf_v2(values).value
        independent_l2 = math.sqrt(
            math.fsum(float(value) * float(value) for value in values)
        )
        independent_linf = max(abs(float(value)) for value in values)
        assert math.isclose(tree_l2, independent_l2, rel_tol=4.0e-15)
        assert tree_linf == independent_linf


def test_gpu_tree_lassq_scale_first_extremes_and_signed_zero() -> None:
    maximum = float(np.finfo(np.float64).max)
    tiny = float(np.nextafter(np.float64(0.0), np.float64(1.0)))

    assert fgmres_gpu_tree_l2_v2([3.0, 4.0]).value == 5.0
    assert fgmres_gpu_tree_linf_v2([3.0, -4.0]).value == 4.0
    assert fgmres_gpu_tree_l2_v2([maximum]).value == maximum
    assert fgmres_gpu_tree_l2_v2([tiny]).value == tiny
    for reduction in (
        fgmres_gpu_tree_l2_v2([-0.0, 0.0]),
        fgmres_gpu_tree_linf_v2([-0.0, 0.0]),
    ):
        assert reduction.value == 0.0
        assert math.copysign(1.0, reduction.value) == 1.0

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as overflow:
        fgmres_gpu_tree_l2_v2([maximum, maximum])
    assert overflow.value.code == "fgmres_gpu_tree_l2_overflow"


@pytest.mark.parametrize("value", (float("nan"), float("inf"), -float("inf")))
def test_gpu_tree_reductions_reject_nonfinite_input(value: float) -> None:
    for operation in (fgmres_gpu_tree_l2_v2, fgmres_gpu_tree_linf_v2):
        with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
            operation([1.0, value])
        assert error.value.code == "fgmres_gpu_tree_vector_nonfinite"


def test_initial_replay_uses_explicit_b_minus_a_x0_and_dual_gate() -> None:
    arguments = {
        "row_ptr": np.array([0, 1, 2], dtype="<i4"),
        "column_indices": np.array([0, 1], dtype="<i4"),
        "values": np.array([2.0, 3.0], dtype="<f8"),
        "rhs": np.array([3.0, -2.0], dtype="<f8"),
        "initial_solution": np.array([1.0, -1.0], dtype="<f8"),
        "absolute_tolerance": 0.0,
        "relative_tolerance": 0.5,
        "authoritative_tolerance": 0.2,
        "max_iterations": 5,
    }
    replay = replay_fgmres_gpu_tree_initial_v2(**arguments)

    assert replay.solution_x.tolist() == [1.0, -1.0]
    assert replay.operator_value.tolist() == [2.0, -3.0]
    assert replay.true_residual.tolist() == [1.0, 1.0]
    # Scale-first tree rounding is intentionally distinct from sqrt(3**2+2**2).
    assert replay.rhs_l2.value == 3.6055512754639896
    assert replay.rhs_linf.value == 3.0
    assert replay.residual_l2.value == math.sqrt(2.0)
    assert replay.residual_linf.value == 1.0
    assert replay.solver_tolerance_l2 == 0.5 * 3.6055512754639896
    assert replay.scaled_residual_linf == 1.0 / 3.0
    assert replay.solver_l2_passed is True
    assert replay.authoritative_linf_passed is False
    assert replay.terminal_status == "not_terminal"
    assert replay.termination_code == "none"
    assert replay.operator_apply_count == 1
    for array in (replay.solution_x, replay.operator_value, replay.true_residual):
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array[0] = 0.0

    converged = replay_fgmres_gpu_tree_initial_v2(
        **{**arguments, "authoritative_tolerance": 0.4}
    )
    assert converged.terminal_status == "converged"
    assert converged.termination_code == "converged_initial_true_residual"

    exhausted = replay_fgmres_gpu_tree_initial_v2(**{**arguments, "max_iterations": 0})
    assert exhausted.terminal_status == "max_iterations"
    assert exhausted.termination_code == "max_iterations_exhausted"


def test_initial_replay_zero_rhs_and_single_gate_paths() -> None:
    base = {
        "row_ptr": [0, 1],
        "column_indices": [0],
        "values": [2.0],
        "rhs": [0.0],
        "initial_solution": [0.0],
        "absolute_tolerance": 1.0e-30,
        "relative_tolerance": 0.0,
        "authoritative_tolerance": 0.0,
        "max_iterations": 0,
    }
    zero = replay_fgmres_gpu_tree_initial_v2(**base)
    assert zero.terminal_status == "converged"
    assert zero.scaled_residual_linf == 0.0

    authoritative_only = replay_fgmres_gpu_tree_initial_v2(
        **{
            **base,
            "initial_solution": [0.25],
            "authoritative_tolerance": 1.0,
        }
    )
    assert authoritative_only.solver_l2_passed is False
    assert authoritative_only.authoritative_linf_passed is True
    assert authoritative_only.terminal_status == "max_iterations"

    solver_only = replay_fgmres_gpu_tree_initial_v2(
        **{
            **base,
            "initial_solution": [0.25],
            "absolute_tolerance": 1.0,
            "authoritative_tolerance": 0.1,
        }
    )
    assert solver_only.solver_l2_passed is True
    assert solver_only.authoritative_linf_passed is False
    assert solver_only.terminal_status == "max_iterations"


def test_initial_replay_csr_and_arithmetic_fail_closed() -> None:
    base = {
        "row_ptr": [0, 1],
        "column_indices": [0],
        "values": [1.0],
        "rhs": [0.0],
        "initial_solution": [0.0],
        "absolute_tolerance": 1.0e-30,
        "relative_tolerance": 0.0,
        "authoritative_tolerance": 0.0,
        "max_iterations": 1,
    }
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as csr:
        replay_fgmres_gpu_tree_initial_v2(**{**base, "row_ptr": [0, 2]})
    assert csr.value.code == "fgmres_gpu_tree_csr_invalid"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as fractional_csr:
        replay_fgmres_gpu_tree_initial_v2(**{**base, "row_ptr": [0.0, 1.0]})
    assert fractional_csr.value.code == "fgmres_gpu_tree_csr_type_invalid"

    for updates in (
        {
            "row_ptr": [0, 2, 2],
            "column_indices": [1, 0],
            "values": [1.0, 1.0],
            "rhs": [0.0, 0.0],
            "initial_solution": [0.0, 0.0],
        },
        {
            "row_ptr": [0, 1, 1],
            "column_indices": [0],
            "values": [1.0],
            "rhs": [0.0, 0.0],
            "initial_solution": [0.0, 0.0],
        },
    ):
        with pytest.raises(FgmresGpuTreeReferenceV2Error) as csr_layout:
            replay_fgmres_gpu_tree_initial_v2(**{**base, **updates})
        assert csr_layout.value.code == "fgmres_gpu_tree_csr_invalid"

    maximum = float(np.finfo(np.float64).max)
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as operator:
        replay_fgmres_gpu_tree_initial_v2(
            **{**base, "values": [maximum], "initial_solution": [2.0]}
        )
    assert operator.value.code == "fgmres_gpu_tree_operator_arithmetic_overflow"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as residual:
        replay_fgmres_gpu_tree_initial_v2(
            **{
                **base,
                "values": [-maximum],
                "rhs": [maximum],
                "initial_solution": [1.0],
            }
        )
    assert residual.value.code == "fgmres_gpu_tree_residual_arithmetic_overflow"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as gate:
        replay_fgmres_gpu_tree_initial_v2(
            **{
                **base,
                "rhs": [maximum],
                "relative_tolerance": maximum,
            }
        )
    assert gate.value.code == "fgmres_gpu_tree_gate_arithmetic_overflow"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as empty_tolerance:
        replay_fgmres_gpu_tree_initial_v2(
            **{
                **base,
                "absolute_tolerance": 0.0,
                "relative_tolerance": 0.0,
            }
        )
    assert empty_tolerance.value.code == "fgmres_gpu_tree_tolerance_empty"

    for invalid in (True, -1, 4097, 1.0):
        with pytest.raises(FgmresGpuTreeReferenceV2Error) as iterations:
            replay_fgmres_gpu_tree_initial_v2(**{**base, "max_iterations": invalid})
        assert iterations.value.code == "fgmres_gpu_tree_max_iterations_invalid"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as complex_vector:
        fgmres_gpu_tree_l2_v2(np.array([1.0 + 2.0j]))
    assert complex_vector.value.code == "fgmres_gpu_tree_vector_type_invalid"


@pytest.mark.parametrize(
    ("count", "stages"),
    (
        (1, (1,)),
        (255, (1,)),
        (256, (1,)),
        (511, (1,)),
        (512, (1,)),
        (513, (2, 1)),
        (512 * 512 + 1, (513, 2, 1)),
    ),
)
def test_gpu_tree_dot_uses_exact_product_then_sum_stage_boundaries(
    count: int,
    stages: tuple[int, ...],
) -> None:
    left = np.ones(count, dtype="<f8")
    right = np.ones(count, dtype="<f8")

    reduction = fgmres_gpu_tree_dot_v2(left, right)

    assert reduction.operation == "dot_fp64"
    assert reduction.value_count == count
    assert reduction.stage_output_counts == stages
    assert reduction.value == float(count)


def test_gpu_tree_dot_is_deterministic_and_canonicalizes_signed_zero() -> None:
    left = np.arange(1.0, 514.0, dtype="<f8")
    right = np.linspace(-3.0, 7.0, 513, dtype="<f8")
    first = fgmres_gpu_tree_dot_v2(left, right)
    second = fgmres_gpu_tree_dot_v2(left.copy(), right.copy())
    negative = fgmres_gpu_tree_dot_v2([1.0, 2.0], [-3.0, -4.0])
    zero = fgmres_gpu_tree_dot_v2([-0.0, 0.0], [2.0, -3.0])

    assert first == second
    assert first.stage_output_counts == (2, 1)
    assert math.isclose(
        first.value,
        math.fsum(float(a) * float(b) for a, b in zip(left, right, strict=True)),
        rel_tol=4.0e-15,
    )
    assert negative.value == -11.0
    assert zero.value == 0.0
    assert math.copysign(1.0, zero.value) == 1.0


def test_gpu_tree_dot_rejects_bad_shapes_types_nonfinite_and_overflow() -> None:
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as shape:
        fgmres_gpu_tree_dot_v2([1.0], [1.0, 2.0])
    assert shape.value.code == "fgmres_gpu_tree_dot_shape_mismatch"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as bad_type:
        fgmres_gpu_tree_dot_v2(np.array([1.0 + 0.0j]), [1.0])
    assert bad_type.value.code == "fgmres_gpu_tree_vector_type_invalid"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as nonfinite:
        fgmres_gpu_tree_dot_v2([1.0], [float("nan")])
    assert nonfinite.value.code == "fgmres_gpu_tree_vector_nonfinite"

    maximum = float(np.finfo(np.float64).max)
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as product:
        fgmres_gpu_tree_dot_v2([maximum], [2.0])
    assert product.value.code == "fgmres_gpu_tree_dot_arithmetic_overflow"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as addition:
        fgmres_gpu_tree_dot_v2([maximum, maximum], [1.0, 1.0])
    assert addition.value.code == "fgmres_gpu_tree_dot_arithmetic_overflow"


def test_first_arnoldi_column_without_dgks_normalizes_v1() -> None:
    replay = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, -0.0],
        jacobi_inverse=[2.0, 3.0],
    )

    assert replay.basis_v0.tolist() == [1.0, 0.0]
    assert replay.jacobi_z0.tolist() == [2.0, 0.0]
    assert replay.operator_work.tolist() == [0.0, 2.0]
    assert replay.work_before_l2.value == 2.0
    assert replay.h00_first_dot.value == 0.0
    assert replay.h00_first_dot.stage_output_counts == (1,)
    assert replay.work_after_first.tolist() == [0.0, 2.0]
    assert replay.after_first_l2.value == 2.0
    assert replay.dgks_second_pass is False
    assert replay.reorthogonalization_count == 0
    assert replay.h00_second_dot is None
    assert replay.h00_first_coefficient == 0.0
    assert replay.h00_second_coefficient == 0.0
    assert replay.h00 == 0.0
    assert replay.h10_l2.value == 2.0
    assert replay.breakdown is False
    assert replay.invariant_breakdown is False
    assert replay.basis_v1.tolist() == [0.0, 1.0]
    assert replay.operator_apply_count == 1
    _assert_replay_arrays_immutable_and_canonical(replay)


def test_first_arnoldi_column_dgks_second_pass_accumulates_h00() -> None:
    replay = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 0],
        values=[1.0, 1.0e-8],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
    )

    assert replay.operator_work.tolist() == [1.0, 1.0e-8]
    assert replay.work_after_first.tolist() == [0.0, 1.0e-8]
    assert replay.dgks_second_pass is True
    assert replay.reorthogonalization_count == 1
    assert replay.h00_first_coefficient == 1.0
    assert replay.h00_second_dot is not None
    assert replay.h00_second_dot.value == 0.0
    assert replay.h00_second_dot.stage_output_counts == (1,)
    assert replay.h00_second_coefficient == 0.0
    assert replay.h00 == 1.0
    assert replay.work_after_final.tolist() == [0.0, 1.0e-8]
    assert replay.h10_l2.value == 1.0e-8
    assert replay.breakdown is False
    assert replay.basis_v1.tolist() == [0.0, 1.0]
    _assert_replay_arrays_immutable_and_canonical(replay)


def test_first_arnoldi_column_dgks_uses_strict_point_717_boundary() -> None:
    eta = 0.717
    tangential = math.sqrt(1.0 - eta * eta)
    at_boundary = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 0],
        values=[tangential, eta],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
    )

    assert at_boundary.work_before_l2.value == 1.0
    assert at_boundary.after_first_l2.value == eta
    assert at_boundary.dgks_second_pass is False

    below = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 0],
        values=[tangential, math.nextafter(eta, 0.0)],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
    )
    assert below.after_first_l2.value < 0.717 * below.work_before_l2.value
    assert below.dgks_second_pass is True


def test_first_arnoldi_column_breakdown_returns_immutable_positive_zero_v1() -> None:
    replay = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 1],
        values=[1.0, 1.0],
        basis_v0=[1.0, -0.0],
        jacobi_inverse=[1.0, 1.0],
    )

    assert replay.dgks_second_pass is True
    assert replay.reorthogonalization_count == 1
    assert replay.h00_first_coefficient == 1.0
    assert replay.h00_second_coefficient == 0.0
    assert replay.h00 == 1.0
    assert replay.h10_l2.value == 0.0
    assert replay.breakdown_threshold == 64.0 * np.finfo(np.float64).eps
    assert replay.breakdown is True
    assert replay.invariant_breakdown is True
    assert replay.basis_v1.tolist() == [0.0, 0.0]
    assert not replay.basis_v1.flags.writeable
    for value in replay.basis_v1:
        assert math.copysign(1.0, float(value)) == 1.0
    _assert_replay_arrays_immutable_and_canonical(replay)


def test_first_arnoldi_column_multiblock_dot_stage_counts_are_preserved() -> None:
    size = 513
    row_ptr = np.arange(size + 1, dtype="<i4")
    columns = np.arange(size, dtype="<i4")
    values = np.ones(size, dtype="<f8")
    basis = np.zeros(size, dtype="<f8")
    basis[0] = 1.0
    replay = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        row_ptr=row_ptr,
        column_indices=columns,
        values=values,
        basis_v0=basis,
        jacobi_inverse=np.ones(size, dtype="<f8"),
    )

    assert replay.h00_first_dot.stage_output_counts == (2, 1)
    assert replay.h00_second_dot is not None
    assert replay.h00_second_dot.stage_output_counts == (2, 1)
    assert replay.invariant_breakdown is True


def test_first_arnoldi_column_strict_validation_and_extreme_fail_closed() -> None:
    base = {
        "row_ptr": [0, 1, 2],
        "column_indices": [0, 1],
        "values": [1.0, 1.0],
        "basis_v0": [1.0, 0.0],
        "jacobi_inverse": [1.0, 1.0],
    }
    for inverse in ([1.0], [1.0, 0.0], [1.0, -1.0]):
        with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
            replay_fgmres_gpu_tree_first_arnoldi_column_v2(
                **{**base, "jacobi_inverse": inverse}
            )
        assert error.value.code in {
            "fgmres_gpu_tree_jacobi_shape_mismatch",
            "fgmres_gpu_tree_jacobi_inverse_not_positive",
        }

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as nonfinite_inverse:
        replay_fgmres_gpu_tree_first_arnoldi_column_v2(
            **{**base, "jacobi_inverse": [1.0, float("inf")]}
        )
    assert nonfinite_inverse.value.code == "fgmres_gpu_tree_vector_nonfinite"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as unsorted:
        replay_fgmres_gpu_tree_first_arnoldi_column_v2(
            **{
                **base,
                "row_ptr": [0, 2, 2],
                "column_indices": [1, 0],
            }
        )
    assert unsorted.value.code == "fgmres_gpu_tree_csr_invalid"

    maximum = float(np.finfo(np.float64).max)
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as jacobi_overflow:
        replay_fgmres_gpu_tree_first_arnoldi_column_v2(
            **{
                **base,
                "basis_v0": [maximum, 0.0],
                "jacobi_inverse": [2.0, 1.0],
            }
        )
    assert jacobi_overflow.value.code == "fgmres_gpu_tree_jacobi_arithmetic_overflow"

    tiny = float(np.nextafter(np.float64(0.0), np.float64(1.0)))
    tiny_replay = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        **{
            **base,
            "values": [tiny, tiny],
            "basis_v0": [1.0, 0.0],
        }
    )
    assert tiny_replay.work_before_l2.value == tiny
    assert tiny_replay.breakdown_threshold == 0.0
    assert tiny_replay.invariant_breakdown is True


@pytest.mark.parametrize(
    ("values", "expected_dgks", "expected_reorthogonalizations"),
    (
        ([1.0, 1.0], False, 0),
        ([1.0, 1.0e-8], True, 1),
    ),
)
def test_first_column_through_givens_reuses_exact_gpu_tree_column_values(
    values: list[float],
    expected_dgks: bool,
    expected_reorthogonalizations: int,
) -> None:
    if expected_dgks:
        columns = [0, 0]
    else:
        columns = [1, 0]
    replay = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=[0, 1, 2],
        column_indices=columns,
        values=values,
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=2,
    )
    legacy = replay_fgmres_gpu_tree_first_arnoldi_column_v2(
        row_ptr=[0, 1, 2],
        column_indices=columns,
        values=values,
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
    )

    assert isinstance(
        replay,
        FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2,
    )
    np.testing.assert_array_equal(
        replay.first_column.work_after_final, legacy.work_after_final
    )
    assert replay.first_column.h00 == legacy.h00
    assert legacy.operator_apply_count == 1
    assert replay.first_column.dgks_second_pass is expected_dgks
    assert replay.first_column.h00_second_dot == legacy.h00_second_dot
    assert replay.first_column.h10_l2 == legacy.h10_l2
    assert replay.breakdown_tau == math.ldexp(1.0, -46)
    assert replay.h_next_breakdown_threshold == (
        math.ldexp(1.0, -46) * legacy.work_before_l2.value
    )
    assert replay.reorthogonalization_count == expected_reorthogonalizations
    assert replay.effective_iterations == 1
    assert replay.arnoldi_step_count == 1
    assert replay.effective_arnoldi_dimension == 1
    assert replay.operator_apply_count == 2
    assert replay.preconditioner_apply_count == 1
    assert replay.invariant_breakdown is False
    assert replay.candidate_reason_bits == 0
    assert replay.candidate_required is False
    assert replay.phase == "arnoldi"
    np.testing.assert_array_equal(replay.basis_v1, legacy.basis_v1)


def test_first_column_through_givens_preserves_negative_hessenberg_sign() -> None:
    replay = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 0],
        values=[-0.1, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=2,
    )

    assert replay.first_column.dgks_second_pass is False
    assert replay.unrotated_h00 == -0.1
    assert replay.unrotated_h10 == 1.0
    assert replay.rotation_norm == math.hypot(-0.1, 1.0)
    assert replay.cosine0 == -0.1 / replay.rotation_norm
    assert replay.cosine0 < 0.0
    assert replay.sine0 == 1.0 / replay.rotation_norm
    assert replay.rotated_h00 == replay.rotation_norm
    assert replay.rotated_h10 == 0.0
    assert math.copysign(1.0, replay.rotated_h10) == 1.0
    assert replay.g0 == replay.cosine0 * 2.0
    assert replay.g0 < 0.0
    assert replay.g1 == -replay.sine0 * 2.0
    assert replay.estimated_residual_l2 == abs(replay.g1)
    assert replay.candidate_required is False
    assert replay.phase == "arnoldi"


def test_first_column_through_givens_exact_breakdown_sets_reason_bits() -> None:
    replay = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 1],
        values=[0.0, -0.0],
        basis_v0=[1.0, -0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=2,
    )

    assert replay.h_next_invariant_breakdown is True
    assert replay.rotation_breakdown is True
    assert replay.invariant_breakdown is True
    assert replay.basis_v1.tolist() == [0.0, 0.0]
    assert replay.cosine0 == 1.0
    assert replay.sine0 == 0.0
    assert replay.rotated_h00 == 0.0
    assert replay.rotated_h10 == 0.0
    assert replay.g0 == 2.0
    assert replay.g1 == 0.0
    assert replay.estimated_residual_l2 == 0.0
    assert replay.candidate_reason_bits == (1 << 0) | (1 << 1)
    assert replay.candidate_required is True
    assert replay.phase == "candidate"
    assert replay.reorthogonalization_count == 0


def test_first_column_through_givens_cycle_end_and_tolerance_triggers() -> None:
    arguments = {
        "row_ptr": [0, 1, 2],
        "column_indices": [1, 0],
        "values": [1.0, 1.0],
        "basis_v0": [1.0, 0.0],
        "jacobi_inverse": [1.0, 1.0],
        "cycle_beta": 2.0,
    }
    cycle_end = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        **arguments,
        solver_tolerance_l2=0.0,
        cycle_width=1,
    )
    tolerance = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        **arguments,
        solver_tolerance_l2=2.0,
        cycle_width=2,
    )

    assert cycle_end.estimated_residual_l2 == 2.0
    assert cycle_end.candidate_reason_bits == 1 << 2
    assert cycle_end.candidate_required is True
    assert cycle_end.phase == "candidate"
    assert tolerance.estimated_residual_l2 == 2.0
    assert tolerance.candidate_reason_bits == 1 << 0
    assert tolerance.candidate_required is True
    assert tolerance.phase == "candidate"


def test_first_column_through_givens_scalar_and_arithmetic_validation() -> None:
    base = {
        "row_ptr": [0, 1, 2],
        "column_indices": [1, 0],
        "values": [1.0, 1.0],
        "basis_v0": [1.0, 0.0],
        "jacobi_inverse": [1.0, 1.0],
        "cycle_beta": 2.0,
        "solver_tolerance_l2": 0.0,
        "cycle_width": 2,
    }
    for value in (True, "2", [2.0]):
        with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
            replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
                **{**base, "cycle_beta": value}
            )
        assert error.value.code == "fgmres_gpu_tree_cycle_beta_type_invalid"
    for value in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
            replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
                **{**base, "cycle_beta": value}
            )
        assert error.value.code == "fgmres_gpu_tree_cycle_beta_invalid"

    for value in (True, "0", [0.0]):
        with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
            replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
                **{**base, "solver_tolerance_l2": value}
            )
        assert error.value.code == "fgmres_gpu_tree_tolerance_type_invalid"
    for value in (-1.0, float("nan"), float("inf")):
        with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
            replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
                **{**base, "solver_tolerance_l2": value}
            )
        assert error.value.code == "fgmres_gpu_tree_tolerance_invalid"

    for value in (True, 0, 17, 1.0):
        with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
            replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
                **{**base, "cycle_width": value}
            )
        assert error.value.code == "fgmres_gpu_tree_cycle_width_invalid"

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as nonfinite:
        replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
            **{**base, "basis_v0": [1.0, float("nan")]}
        )
    assert nonfinite.value.code == "fgmres_gpu_tree_vector_nonfinite"

    maximum = float(np.finfo(np.float64).max)
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as overflow:
        replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
            **{
                **base,
                "basis_v0": [maximum, 0.0],
                "jacobi_inverse": [2.0, 1.0],
            }
        )
    assert overflow.value.code == "fgmres_gpu_tree_jacobi_arithmetic_overflow"


def test_first_column_through_givens_is_immutable_and_canonicalizes_zero() -> None:
    replay = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, -0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=2,
    )

    assert not replay.basis_v1.flags.writeable
    with pytest.raises(ValueError):
        replay.basis_v1[0] = 1.0
    with pytest.raises(FrozenInstanceError):
        replay.phase = "candidate"  # type: ignore[misc]
    _assert_replay_arrays_immutable_and_canonical(replay.first_column)
    for value in (
        replay.unrotated_h00,
        replay.cosine0,
        replay.rotated_h10,
        replay.g0,
    ):
        assert value == 0.0
        assert math.copysign(1.0, value) == 1.0
    for value in replay.basis_v1:
        if float(value) == 0.0:
            assert math.copysign(1.0, float(value)) == 1.0


def test_candidate_preparation_false_gate_is_a_numeric_noop() -> None:
    through = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=2,
    )
    assert through.candidate_required is False

    preparation = prepare_fgmres_gpu_tree_first_column_candidate_v2(
        through_givens=through,
        committed_solution=object(),
    )

    assert isinstance(
        preparation,
        FgmresGpuTreeFirstColumnCandidatePreparationV2,
    )
    assert preparation.candidate_required is False
    assert preparation.candidate_reason_bits == 0
    assert preparation.backsubstitution_attempted is False
    assert preparation.triangular_scale is None
    assert preparation.pivot_floor is None
    assert preparation.triangular_breakdown is False
    assert preparation.invariant_breakdown is through.invariant_breakdown is False
    assert preparation.y0 is None
    assert preparation.trial_x is None
    assert preparation.solution_update_l2 is None
    assert preparation.candidate_vector_valid is False
    assert preparation.operator_apply_count == through.operator_apply_count == 2
    assert preparation.preconditioner_apply_count == 1
    assert preparation.effective_iterations == 1
    assert preparation.checkpoint_decision_included is False
    assert preparation.checkpoint_commit_included is False


def test_candidate_preparation_valid_happy_column_uses_exact_update_tree() -> None:
    preparation = replay_fgmres_gpu_tree_first_column_candidate_preparation_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 1],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=2,
        committed_solution=[0.5, -0.0],
    )

    assert preparation.candidate_reason_bits == (1 << 0) | (1 << 1)
    assert preparation.candidate_required is True
    assert preparation.backsubstitution_attempted is True
    assert preparation.triangular_scale == 1.0
    assert preparation.pivot_floor == math.ldexp(1.0, -46)
    assert preparation.triangular_breakdown is False
    assert preparation.invariant_breakdown is True
    assert preparation.y0 == 2.0
    np.testing.assert_array_equal(preparation.trial_x, [2.5, 0.0])
    assert preparation.solution_update_l2 is not None
    assert preparation.solution_update_l2.operation == "lassq_l2"
    assert preparation.solution_update_l2.stage_output_counts == (1,)
    assert preparation.solution_update_l2.value == 2.0
    assert preparation.candidate_vector_valid is True
    assert preparation.operator_apply_count == 2
    assert preparation.preconditioner_apply_count == 1


def test_candidate_preparation_zero_pivot_breaks_without_reading_solution() -> None:
    through = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
    )
    assert through.invariant_breakdown is False

    preparation = prepare_fgmres_gpu_tree_first_column_candidate_v2(
        through_givens=replace(through, rotated_h00=0.0),
        committed_solution=object(),
    )

    assert preparation.candidate_required is True
    assert preparation.backsubstitution_attempted is True
    assert preparation.triangular_scale == 0.0
    assert preparation.pivot_floor == 0.0
    assert preparation.triangular_breakdown is True
    assert through.invariant_breakdown is False
    assert preparation.invariant_breakdown is True
    assert preparation.y0 is None
    assert preparation.trial_x is None
    assert preparation.solution_update_l2 is None
    assert preparation.candidate_vector_valid is False


@pytest.mark.parametrize(
    ("pivot", "g0", "expected_y0", "expected_floor"),
    (
        (-2.0, 4.0, -2.0, 2.0 * math.ldexp(1.0, -46)),
        (
            float(np.nextafter(np.float64(0.0), np.float64(1.0))),
            float(np.nextafter(np.float64(0.0), np.float64(1.0))),
            1.0,
            0.0,
        ),
    ),
)
def test_candidate_preparation_signed_and_subnormal_pivots_are_scale_relative(
    pivot: float,
    g0: float,
    expected_y0: float,
    expected_floor: float,
) -> None:
    through = _candidate_identity_through_givens()
    synthetic = replace(through, rotated_h00=pivot, g0=g0)

    preparation = prepare_fgmres_gpu_tree_first_column_candidate_v2(
        through_givens=synthetic,
        committed_solution=[0.0, 0.0],
    )

    assert preparation.triangular_scale == abs(pivot)
    assert preparation.pivot_floor == expected_floor
    assert preparation.triangular_breakdown is False
    assert preparation.invariant_breakdown is through.invariant_breakdown
    assert preparation.y0 == expected_y0
    np.testing.assert_array_equal(preparation.trial_x, [expected_y0, 0.0])
    assert preparation.solution_update_l2 is not None
    assert preparation.solution_update_l2.value == abs(expected_y0)


def test_candidate_preparation_rejects_backsolve_trial_and_update_overflow() -> None:
    through = _candidate_identity_through_givens()
    maximum = float(np.finfo(np.float64).max)
    tiny = float(np.nextafter(np.float64(0.0), np.float64(1.0)))

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as backsolve:
        prepare_fgmres_gpu_tree_first_column_candidate_v2(
            through_givens=replace(
                through,
                rotated_h00=tiny,
                g0=maximum,
            ),
            committed_solution=[0.0, 0.0],
        )
    assert backsolve.value.code == "fgmres_gpu_tree_triangular_arithmetic_overflow"

    overflowing_z = replace(
        through.first_column,
        jacobi_z0=np.array([2.0, 0.0], dtype="<f8"),
    )
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as trial:
        prepare_fgmres_gpu_tree_first_column_candidate_v2(
            through_givens=replace(
                through,
                first_column=overflowing_z,
                rotated_h00=1.0,
                g0=maximum,
            ),
            committed_solution=[0.0, 0.0],
        )
    assert trial.value.code == "fgmres_gpu_tree_trial_arithmetic_overflow"

    overflowing_norm_z = replace(
        through.first_column,
        jacobi_z0=np.array([maximum, maximum], dtype="<f8"),
    )
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as update:
        prepare_fgmres_gpu_tree_first_column_candidate_v2(
            through_givens=replace(
                through,
                first_column=overflowing_norm_z,
                rotated_h00=1.0,
                g0=1.0,
            ),
            committed_solution=[0.0, 0.0],
        )
    assert update.value.code == "fgmres_gpu_tree_l2_overflow"


def test_candidate_preparation_is_immutable_and_canonicalizes_zero() -> None:
    preparation = replay_fgmres_gpu_tree_first_column_candidate_preparation_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, -0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=[-0.0, 0.0],
    )

    assert preparation.candidate_required is True
    assert preparation.candidate_vector_valid is True
    assert preparation.through_givens.invariant_breakdown is False
    assert preparation.invariant_breakdown is False
    assert preparation.y0 == 0.0
    assert math.copysign(1.0, preparation.y0) == 1.0
    assert preparation.trial_x is not None
    assert not preparation.trial_x.flags.writeable
    assert not np.signbit(preparation.trial_x).any()
    assert preparation.solution_update_l2 is not None
    assert preparation.solution_update_l2.value == 0.0
    assert math.copysign(1.0, preparation.solution_update_l2.value) == 1.0
    with pytest.raises(ValueError):
        preparation.trial_x[0] = 1.0
    with pytest.raises(FrozenInstanceError):
        preparation.candidate_vector_valid = False  # type: ignore[misc]


def test_candidate_residual_active_invariant_replay_publishes_exact_metrics() -> None:
    preparation = _active_candidate_preparation(committed_solution=[0.5, 0.0])

    replay = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=preparation,
        row_ptr=[0, 1, 2],
        column_indices=[0, 1],
        values=[1.0, 1.0],
        reduced_load=[3.0, 0.0],
    )

    assert type(replay) is FgmresGpuTreeFirstColumnCandidateResidualReplayV2
    assert replay.candidate_required is True
    assert replay.candidate_reason_bits == 3
    assert replay.invariant_breakdown is True
    assert replay.phase == "candidate"
    assert replay.candidate_replay_attempted is True
    assert replay.candidate_replay_valid is True
    np.testing.assert_array_equal(replay.candidate_operator_value, [2.5, 0.0])
    np.testing.assert_array_equal(replay.candidate_true_residual, [0.5, 0.0])
    assert replay.candidate_operator is replay.candidate_operator_value
    assert replay.candidate_residual is replay.candidate_true_residual
    assert replay.candidate_l2 is not None
    assert replay.candidate_linf is not None
    assert replay.candidate_l2.operation == "lassq_l2"
    assert replay.candidate_linf.operation == "abs_max_linf"
    assert replay.candidate_l2.value == replay.candidate_linf.value == 0.5
    assert replay.candidate_l2.stage_output_counts == (1,)
    assert replay.candidate_linf.stage_output_counts == (1,)
    assert replay.solution_update_l2 is preparation.solution_update_l2
    assert replay.trial_x_l2 is replay.committed_x_l2 is None
    assert replay.reduction_valid_mask == 1792
    assert replay.operator_apply_count == 3
    assert replay.preconditioner_apply_count == 1
    assert replay.effective_iterations == replay.arnoldi_step_count == 1
    assert replay.effective_arnoldi_dimension == 1
    assert replay.checkpoint_decision_included is False
    assert replay.checkpoint_commit_included is False
    assert replay.solution_and_true_residual_committed is False


def test_candidate_residual_raw_cycle_candidate_is_noninvariant_and_exact() -> None:
    replay = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=[0.5, 0.0],
        reduced_load=[0.0, 0.5],
    )

    assert replay.candidate_reason_bits == 1 << 2
    assert replay.invariant_breakdown is False
    assert replay.triangular_breakdown is False
    assert replay.candidate_replay_valid is True
    np.testing.assert_array_equal(replay.candidate_operator_value, [0.0, 0.5])
    np.testing.assert_array_equal(replay.candidate_true_residual, [0.0, 0.0])
    assert replay.candidate_l2 is not None and replay.candidate_l2.value == 0.0
    assert replay.candidate_linf is not None and replay.candidate_linf.value == 0.0
    assert replay.reduction_valid_mask == 1792


def test_candidate_residual_false_gate_ignores_all_external_numeric_inputs() -> None:
    preparation = _candidate_false_preparation()

    replay = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=preparation,
        row_ptr=object(),
        column_indices=object(),
        values=object(),
        reduced_load=object(),
    )

    assert replay.candidate_required is False
    assert replay.phase == "arnoldi"
    assert replay.candidate_replay_attempted is False
    assert replay.candidate_replay_valid is False
    assert replay.candidate_operator_value is None
    assert replay.candidate_true_residual is None
    assert replay.candidate_l2 is replay.candidate_linf is None
    assert replay.solution_update_l2 is None
    assert replay.reduction_valid_mask == 0
    assert replay.operator_apply_count == 2
    assert replay.checkpoint_decision_included is False
    assert replay.checkpoint_commit_included is False


def test_candidate_residual_triangular_breakdown_ignores_external_numeric_inputs() -> (
    None
):
    preparation = _triangular_breakdown_preparation()

    replay = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=preparation,
        row_ptr=object(),
        column_indices=object(),
        values=object(),
        reduced_load=object(),
    )

    assert replay.candidate_required is True
    assert replay.triangular_breakdown is True
    assert replay.invariant_breakdown is True
    assert replay.phase == "candidate"
    assert replay.candidate_replay_attempted is False
    assert replay.candidate_replay_valid is False
    assert replay.candidate_operator_value is None
    assert replay.candidate_true_residual is None
    assert replay.candidate_l2 is replay.candidate_linf is None
    assert replay.reduction_valid_mask == 0
    assert replay.operator_apply_count == 2


def test_candidate_residual_canonicalizes_signed_zero() -> None:
    replay = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, -0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=[-0.0, 0.0],
        reduced_load=[-0.0, -0.0],
    )

    assert replay.candidate_operator_value is not None
    assert replay.candidate_true_residual is not None
    assert not np.signbit(replay.candidate_operator_value).any()
    assert not np.signbit(replay.candidate_true_residual).any()
    assert replay.candidate_l2 is not None and replay.candidate_l2.value == 0.0
    assert replay.candidate_linf is not None and replay.candidate_linf.value == 0.0
    assert math.copysign(1.0, replay.candidate_l2.value) == 1.0
    assert math.copysign(1.0, replay.candidate_linf.value) == 1.0


def test_candidate_residual_preserves_subnormal_operator_and_tree_metrics() -> None:
    preparation = _active_candidate_preparation(committed_solution=[0.0, 0.0])
    tiny = float(np.nextafter(np.float64(0.0), np.float64(1.0)))

    replay = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=preparation,
        row_ptr=[0, 1, 2],
        column_indices=[0, 1],
        values=[tiny, 1.0],
        reduced_load=[0.0, 0.0],
    )

    assert replay.candidate_operator_value is not None
    assert replay.candidate_operator_value[0] == 2.0 * tiny
    assert replay.candidate_true_residual is not None
    assert replay.candidate_true_residual[0] == -2.0 * tiny
    assert replay.candidate_l2 is not None
    assert replay.candidate_linf is not None
    assert replay.candidate_l2.value == replay.candidate_linf.value == 2.0 * tiny


@pytest.mark.parametrize(
    ("arguments", "code"),
    (
        (
            {
                "row_ptr": [0, 1, 2],
                "column_indices": [0, 1],
                "values": [1.0, 1.0],
                "reduced_load": [math.nan, 0.0],
            },
            "fgmres_gpu_tree_vector_nonfinite",
        ),
        (
            {
                "row_ptr": [0, 2, 2],
                "column_indices": [0, 0],
                "values": [1.0, 1.0],
                "reduced_load": [0.0, 0.0],
            },
            "fgmres_gpu_tree_csr_invalid",
        ),
        (
            {
                "row_ptr": [0, 1, 2],
                "column_indices": [0, 1],
                "values": [math.inf, 1.0],
                "reduced_load": [0.0, 0.0],
            },
            "fgmres_gpu_tree_csr_invalid",
        ),
        (
            {
                "row_ptr": [0, 1, 2],
                "column_indices": [0, 1],
                "values": [1.0, 1.0],
                "reduced_load": [0.0],
            },
            "fgmres_gpu_tree_candidate_residual_shape_mismatch",
        ),
    ),
)
def test_candidate_residual_rejects_active_load_shape_nonfinite_and_csr_errors(
    arguments: dict[str, object],
    code: str,
) -> None:
    preparation = _active_candidate_preparation(committed_solution=[0.0, 0.0])

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
        prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
            candidate_preparation=preparation,
            **arguments,
        )
    assert error.value.code == code


def test_candidate_residual_rejects_operator_residual_and_l2_overflow() -> None:
    preparation = _active_candidate_preparation(committed_solution=[0.0, 0.0])
    maximum = float(np.finfo(np.float64).max)

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as operator:
        prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
            candidate_preparation=preparation,
            row_ptr=[0, 1, 2],
            column_indices=[0, 1],
            values=[maximum, 1.0],
            reduced_load=[0.0, 0.0],
        )
    assert operator.value.code == "fgmres_gpu_tree_operator_arithmetic_overflow"

    overflow_trial = replace(
        preparation,
        trial_x=np.array([maximum, 0.0], dtype="<f8"),
    )
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as residual:
        prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
            candidate_preparation=overflow_trial,
            row_ptr=[0, 1, 2],
            column_indices=[0, 1],
            values=[-1.0, 1.0],
            reduced_load=[maximum, 0.0],
        )
    assert residual.value.code == (
        "fgmres_gpu_tree_candidate_residual_arithmetic_overflow"
    )

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as norm:
        prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
            candidate_preparation=preparation,
            row_ptr=[0, 1, 2],
            column_indices=[0, 1],
            values=[0.0, 0.0],
            reduced_load=[maximum, maximum],
        )
    assert norm.value.code == "fgmres_gpu_tree_l2_overflow"


def test_candidate_residual_multistage_arrays_and_dataclass_are_immutable() -> None:
    count = 513
    basis_v0 = np.zeros(count, dtype="<f8")
    basis_v0[0] = 1.0
    replay = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=np.arange(count + 1, dtype="<i4"),
        column_indices=np.arange(count, dtype="<i4"),
        values=np.ones(count, dtype="<f8"),
        basis_v0=basis_v0,
        jacobi_inverse=np.ones(count, dtype="<f8"),
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=4,
        committed_solution=np.zeros(count, dtype="<f8"),
        reduced_load=np.zeros(count, dtype="<f8"),
    )

    assert replay.candidate_l2 is not None
    assert replay.candidate_linf is not None
    assert replay.candidate_l2.stage_output_counts == (2, 1)
    assert replay.candidate_linf.stage_output_counts == (2, 1)
    assert replay.candidate_l2.value == replay.candidate_linf.value == 2.0
    for array in (replay.candidate_operator_value, replay.candidate_true_residual):
        assert array is not None
        assert array.dtype == np.dtype("<f8")
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array[0] = 1.0
    with pytest.raises(FrozenInstanceError):
        replay.candidate_replay_valid = False  # type: ignore[misc]


def test_candidate_residual_rejects_wrong_or_forged_preparation_state() -> None:
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as source_type:
        prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
            candidate_preparation=object(),  # type: ignore[arg-type]
            row_ptr=object(),
            column_indices=object(),
            values=object(),
            reduced_load=object(),
        )
    assert source_type.value.code == (
        "fgmres_gpu_tree_candidate_residual_source_type_invalid"
    )

    forged = replace(_candidate_false_preparation(), operator_apply_count=3)
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as source_state:
        prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
            candidate_preparation=forged,
            row_ptr=object(),
            column_indices=object(),
            values=object(),
            reduced_load=object(),
        )
    assert source_state.value.code == (
        "fgmres_gpu_tree_candidate_residual_source_state_invalid"
    )


def test_candidate_scale_metrics_inactive_triangular_and_noncycle_are_policy_noops() -> (
    None
):
    inactive = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=_candidate_false_preparation(),
        row_ptr=object(),
        column_indices=object(),
        values=object(),
        reduced_load=object(),
    )
    triangular = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=_triangular_breakdown_preparation(),
        row_ptr=object(),
        column_indices=object(),
        values=object(),
        reduced_load=object(),
    )
    noncycle = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=_active_candidate_preparation(
            committed_solution=[0.5, 0.0]
        ),
        row_ptr=[0, 1, 2],
        column_indices=[0, 1],
        values=[1.0, 1.0],
        reduced_load=[3.0, 0.0],
    )

    for source, expected_mask in (
        (inactive, 0),
        (triangular, 0),
        (noncycle, 1792),
    ):
        replay = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
            candidate_residual=source,
            solver_tolerance_l2=object(),  # type: ignore[arg-type]
            authoritative_tolerance=object(),  # type: ignore[arg-type]
            rhs_linf=object(),  # type: ignore[arg-type]
            initial_residual_l2=object(),  # type: ignore[arg-type]
            divergence_factor=object(),  # type: ignore[arg-type]
            committed_solution=object(),
        )

        assert type(replay) is FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2
        assert replay.candidate_residual is source
        assert replay.planned_cycle_end is bool(source.candidate_reason_bits & 4)
        assert replay.dual_gate_evaluated is False
        assert replay.scaled_candidate_residual_linf is None
        assert replay.solver_l2_passed is None
        assert replay.authoritative_linf_passed is None
        assert replay.dual_gate_passed is None
        assert replay.divergence_evaluated is False
        assert replay.divergence_threshold_l2 is None
        assert replay.divergence_detected is None
        assert replay.candidate_scale_required is False
        assert replay.scale_metrics_required is False
        assert replay.trial_x_l2 is replay.committed_x_l2 is None
        assert replay.x_scale_l2 is None
        assert replay.prior_reduction_valid_mask == expected_mask
        assert replay.trial_x_reduction_valid_mask is None
        assert replay.reduction_valid_mask == expected_mask


def test_candidate_scale_metrics_dual_gate_uses_raw_scaled_linf_and_equality() -> None:
    source = _cycle_end_candidate_residual(reduced_load=[1.0, 2.5])
    assert source.candidate_l2 is not None
    assert source.candidate_linf is not None
    assert source.candidate_l2.value == math.sqrt(5.0)
    assert source.candidate_linf.value == 2.0

    replay = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=source,
        solver_tolerance_l2=math.sqrt(5.0),
        authoritative_tolerance=0.5,
        rhs_linf=4.0,
        initial_residual_l2=object(),  # type: ignore[arg-type]
        divergence_factor=object(),  # type: ignore[arg-type]
        committed_solution=object(),
    )

    assert replay.planned_cycle_end is True
    assert replay.dual_gate_evaluated is True
    assert replay.scaled_candidate_residual_linf == 0.5
    assert replay.solver_l2_passed is True
    assert replay.authoritative_linf_passed is True
    assert replay.dual_gate_passed is True
    assert replay.divergence_evaluated is False
    assert replay.candidate_scale_required is False
    assert replay.trial_x_l2 is replay.committed_x_l2 is None
    assert replay.reduction_valid_mask == 1792


@pytest.mark.parametrize(
    (
        "solver_tolerance_l2",
        "authoritative_tolerance",
        "solver_passed",
        "authoritative_passed",
    ),
    (
        (1.0, 0.0, True, False),
        (0.0, 1.0, False, True),
    ),
)
def test_candidate_scale_metrics_one_gate_only_continues_to_scale_metrics(
    solver_tolerance_l2: float,
    authoritative_tolerance: float,
    solver_passed: bool,
    authoritative_passed: bool,
) -> None:
    source = _cycle_end_candidate_residual(reduced_load=[1.0, 0.5])

    replay = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=source,
        solver_tolerance_l2=solver_tolerance_l2,
        authoritative_tolerance=authoritative_tolerance,
        rhs_linf=1.0,
        initial_residual_l2=0.5,
        divergence_factor=2.0,
        committed_solution=[0.5, 0.0],
    )

    assert replay.solver_l2_passed is solver_passed
    assert replay.authoritative_linf_passed is authoritative_passed
    assert replay.dual_gate_passed is False
    assert replay.divergence_evaluated is True
    assert replay.divergence_threshold_l2 == 1.0
    assert replay.divergence_detected is False
    assert replay.candidate_scale_required is True
    assert replay.candidate_scale_metrics_attempted is True
    assert replay.candidate_scale_metrics_valid is True
    assert replay.trial_x_l2 is not None and replay.trial_x_l2.value == 0.5
    assert replay.committed_x_l2 is not None
    assert replay.committed_x_l2.value == 0.5
    assert replay.trial_x_reduction_valid_mask == 5888
    assert replay.reduction_valid_mask == 7936


def test_candidate_scale_metrics_invariant_short_circuits_divergence_policy() -> None:
    source = _invariant_cycle_candidate_residual()
    assert source.invariant_breakdown is True
    assert source.candidate_reason_bits & (1 << 2)

    replay = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=source,
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
        rhs_linf=0.0,
        initial_residual_l2=object(),  # type: ignore[arg-type]
        divergence_factor=object(),  # type: ignore[arg-type]
        committed_solution=object(),
    )

    assert replay.dual_gate_evaluated is True
    assert replay.dual_gate_passed is False
    assert replay.divergence_evaluated is False
    assert replay.divergence_threshold_l2 is None
    assert replay.candidate_scale_required is False
    assert replay.reduction_valid_mask == 1792


def test_candidate_scale_metrics_divergence_is_strict_and_short_circuits_solution() -> (
    None
):
    equal_source = _cycle_end_candidate_residual(reduced_load=[1.0, 0.5])
    equality = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=equal_source,
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
        rhs_linf=1.0,
        initial_residual_l2=0.5,
        divergence_factor=2.0,
        committed_solution=[0.5, 0.0],
    )
    assert equality.divergence_threshold_l2 == 1.0
    assert equality.divergence_detected is False
    assert equality.candidate_scale_required is True

    above = float(np.nextafter(np.float64(1.0), np.float64(math.inf)))
    diverged_source = _cycle_end_candidate_residual(reduced_load=[above, 0.5])
    diverged = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=diverged_source,
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
        rhs_linf=1.0,
        initial_residual_l2=0.5,
        divergence_factor=2.0,
        committed_solution=object(),
    )
    assert diverged.divergence_threshold_l2 == 1.0
    assert diverged.divergence_detected is True
    assert diverged.candidate_scale_required is False
    assert diverged.trial_x_l2 is diverged.committed_x_l2 is None
    assert diverged.reduction_valid_mask == 1792


def test_candidate_scale_metrics_infinite_divergence_threshold_is_not_diverged() -> (
    None
):
    maximum = float(np.finfo(np.float64).max)
    source = _cycle_end_candidate_residual(reduced_load=[1.0, 0.5])

    replay = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=source,
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
        rhs_linf=1.0,
        initial_residual_l2=maximum,
        divergence_factor=2.0,
        committed_solution=[0.5, 0.0],
    )

    assert replay.divergence_evaluated is True
    assert replay.divergence_threshold_l2 == math.inf
    assert replay.divergence_detected is False
    assert replay.candidate_scale_required is True
    assert replay.reduction_valid_mask == 7936


@pytest.mark.parametrize(
    ("overrides", "code", "path"),
    (
        (
            {"solver_tolerance_l2": math.nan},
            "fgmres_gpu_tree_tolerance_invalid",
            "/solver_tolerance_l2",
        ),
        (
            {"authoritative_tolerance": -1.0},
            "fgmres_gpu_tree_tolerance_invalid",
            "/authoritative_tolerance",
        ),
        (
            {"rhs_linf": math.inf},
            "fgmres_gpu_tree_tolerance_invalid",
            "/rhs_linf",
        ),
        (
            {"initial_residual_l2": math.nan},
            "fgmres_gpu_tree_tolerance_invalid",
            "/initial_residual_l2",
        ),
        (
            {"divergence_factor": 1.0},
            "fgmres_gpu_tree_divergence_factor_invalid",
            "/divergence_factor",
        ),
        (
            {"committed_solution": [math.nan, 0.0]},
            "fgmres_gpu_tree_vector_nonfinite",
            "/committed_solution",
        ),
        (
            {"committed_solution": [0.5]},
            "fgmres_gpu_tree_candidate_scale_solution_shape_mismatch",
            "/committed_solution",
        ),
    ),
)
def test_candidate_scale_metrics_rejects_active_policy_and_solution_errors(
    overrides: dict[str, object],
    code: str,
    path: str,
) -> None:
    arguments: dict[str, object] = {
        "candidate_residual": _cycle_end_candidate_residual(reduced_load=[1.0, 0.5]),
        "solver_tolerance_l2": 0.0,
        "authoritative_tolerance": 0.0,
        "rhs_linf": 1.0,
        "initial_residual_l2": 0.5,
        "divergence_factor": 2.0,
        "committed_solution": [0.5, 0.0],
    }
    arguments.update(overrides)

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
        prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
            **arguments,  # type: ignore[arg-type]
        )
    assert error.value.code == code
    assert error.value.path == path


def test_candidate_scale_metrics_preserves_subnormal_solution_norms() -> None:
    tiny = float(np.nextafter(np.float64(0.0), np.float64(1.0)))
    source = _cycle_end_candidate_residual(
        committed_solution=[tiny, 0.0],
        reduced_load=[1.0, 0.0],
    )

    replay = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=source,
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
        rhs_linf=1.0,
        initial_residual_l2=1.0,
        divergence_factor=2.0,
        committed_solution=[tiny, 0.0],
    )

    assert replay.trial_x_l2 is not None
    assert replay.committed_x_l2 is not None
    assert replay.trial_x_l2.value == tiny
    assert replay.committed_x_l2.value == tiny
    assert replay.reduction_valid_mask == 7936


def test_candidate_scale_metrics_rejects_represented_trial_l2_overflow() -> None:
    maximum = float(np.finfo(np.float64).max)
    reciprocal = 1.0 / maximum
    source = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[reciprocal, reciprocal],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=[maximum, maximum],
        reduced_load=[0.0, 0.0],
    )
    assert source.candidate_l2 is not None
    assert math.isclose(source.candidate_l2.value, math.sqrt(2.0), rel_tol=1.0e-15)

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
        prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
            candidate_residual=source,
            solver_tolerance_l2=0.0,
            authoritative_tolerance=0.0,
            rhs_linf=1.0,
            initial_residual_l2=maximum,
            divergence_factor=2.0,
            committed_solution=object(),
        )
    assert error.value.code == "fgmres_gpu_tree_l2_overflow"
    assert error.value.path == "/values"


def test_candidate_scale_metrics_raw_wrapper_multistage_masks_and_immutability() -> (
    None
):
    count = 513
    row_ptr = np.arange(count + 1, dtype="<i4")
    columns = np.arange(count, dtype="<i4")
    columns[:2] = [1, 0]
    basis_v0 = np.zeros(count, dtype="<f8")
    basis_v0[0] = 1.0
    committed = np.ones(count, dtype="<f8")

    replay = replay_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        row_ptr=row_ptr,
        column_indices=columns,
        values=np.ones(count, dtype="<f8"),
        basis_v0=basis_v0,
        jacobi_inverse=np.ones(count, dtype="<f8"),
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=committed,
        reduced_load=np.full(count, 2.0, dtype="<f8"),
        authoritative_tolerance=0.0,
        rhs_linf=2.0,
        initial_residual_l2=math.sqrt(float(count)),
        divergence_factor=2.0,
    )

    assert replay.candidate_reason_bits == 1 << 2
    assert replay.invariant_breakdown is False
    assert replay.candidate_scale_required is True
    assert replay.trial_x_l2 is not None
    assert replay.committed_x_l2 is not None
    assert replay.trial_x_l2.stage_output_counts == (2, 1)
    assert replay.committed_x_l2.stage_output_counts == (2, 1)
    assert replay.trial_x_l2.value == math.sqrt(float(count))
    assert replay.committed_x_l2.value == math.sqrt(float(count))
    assert replay.prior_reduction_valid_mask == 1792
    assert replay.trial_x_reduction_valid_mask == 5888
    assert replay.reduction_valid_mask == 7936
    source = replay.candidate_residual
    assert replay.effective_iterations == source.effective_iterations
    assert replay.arnoldi_step_count == source.arnoldi_step_count
    assert replay.effective_arnoldi_dimension == source.effective_arnoldi_dimension
    assert replay.reorthogonalization_count == source.reorthogonalization_count
    assert replay.operator_apply_count == source.operator_apply_count == 3
    assert replay.preconditioner_apply_count == source.preconditioner_apply_count
    assert replay.checkpoint_decision_included is False
    assert replay.checkpoint_commit_included is False
    assert replay.solution_and_true_residual_committed is False
    assert replay.x_scale_l2 is None
    with pytest.raises(FrozenInstanceError):
        replay.candidate_scale_required = False  # type: ignore[misc]


def test_candidate_scale_metrics_rejects_wrong_or_forged_residual_state() -> None:
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as source_type:
        prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
            candidate_residual=object(),  # type: ignore[arg-type]
            solver_tolerance_l2=object(),  # type: ignore[arg-type]
            authoritative_tolerance=object(),  # type: ignore[arg-type]
            rhs_linf=object(),  # type: ignore[arg-type]
            initial_residual_l2=object(),  # type: ignore[arg-type]
            divergence_factor=object(),  # type: ignore[arg-type]
            committed_solution=object(),
        )
    assert source_type.value.code == (
        "fgmres_gpu_tree_candidate_scale_metrics_source_type_invalid"
    )

    forged = replace(
        _cycle_end_candidate_residual(reduced_load=[1.0, 0.5]),
        reduction_valid_mask=0,
    )
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as source_state:
        prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
            candidate_residual=forged,
            solver_tolerance_l2=object(),  # type: ignore[arg-type]
            authoritative_tolerance=object(),  # type: ignore[arg-type]
            rhs_linf=object(),  # type: ignore[arg-type]
            initial_residual_l2=object(),  # type: ignore[arg-type]
            divergence_factor=object(),  # type: ignore[arg-type]
            committed_solution=object(),
        )
    assert source_state.value.code == (
        "fgmres_gpu_tree_candidate_scale_metrics_source_state_invalid"
    )


def test_checkpoint_transaction_inactive_is_same_cycle_byte_preserving_noop() -> None:
    source = _checkpoint_inactive_scale_source()
    committed_x = np.array([-0.0, 0.5], dtype="<f8")
    committed_r = np.array([2.0, -0.0], dtype="<f8")

    replay = _checkpoint_transaction(
        source,
        committed_solution=committed_x,
        committed_true_residual=committed_r,
        previous_solution_scale_l2=7.0,
    )

    assert type(replay) is FgmresGpuTreeFirstColumnCheckpointTransactionReplayV2
    assert replay.decision == "candidate_inactive"
    assert replay.commit_required is False
    assert replay.continuation_required is True
    assert replay.continuation_kind == "same_cycle"
    assert replay.row_appended is False
    assert replay.restart_record is None
    assert replay.start_reduction_valid_mask == 0
    assert replay.decide_reduction_valid_mask == 0
    assert replay.commit_reduction_valid_mask == 0
    assert replay.finalize_reduction_valid_mask == 0
    assert replay.active_during_decide is replay.active_during_commit is True
    assert replay.active_after_finalize is True
    assert replay.phase_after_finalize == "arnoldi"
    assert replay.terminal_status == "not_terminal"
    assert replay.terminal_status_code == 0
    assert replay.termination_code == "none"
    assert replay.solution_scale_l2 == 7.0
    np.testing.assert_array_equal(
        replay.solution_x.view("<u8"), committed_x.view("<u8")
    )
    np.testing.assert_array_equal(
        replay.true_residual.view("<u8"), committed_r.view("<u8")
    )
    assert not replay.solution_x.flags.writeable
    assert not replay.true_residual.flags.writeable
    with pytest.raises(FrozenInstanceError):
        replay.commit_required = True  # type: ignore[misc]


def test_checkpoint_transaction_triangular_breakdown_records_without_commit() -> None:
    source = _checkpoint_triangular_scale_source()
    committed_x = np.array([-0.0, 0.5], dtype="<f8")
    committed_r = np.array([2.0, -0.0], dtype="<f8")

    replay = _checkpoint_transaction(
        source,
        committed_solution=committed_x,
        committed_true_residual=committed_r,
        previous_stagnation_checkpoint_count=1,
    )

    assert replay.decision == "triangular_breakdown"
    assert replay.commit_required is False
    assert replay.active_during_commit is True
    assert replay.active_after_finalize is False
    assert replay.terminal_status == "arnoldi_breakdown"
    assert replay.terminal_status_code == 5
    assert replay.termination_code == "arnoldi_triangular_factor_breakdown"
    assert replay.termination_code_value == 30
    assert replay.row_appended is True
    assert type(replay.restart_record) is (
        FgmresGpuTreeFirstColumnCheckpointTransactionRecordV2
    )
    assert replay.restart_record.termination_hint_code == 5
    assert replay.restart_record.flags == 0
    assert replay.restart_record.solution_update_l2 == 0.0
    assert replay.restart_record.true_residual_l2 == 2.0
    assert replay.stagnation_checkpoint_count == 1
    np.testing.assert_array_equal(
        replay.solution_x.view("<u8"), committed_x.view("<u8")
    )
    np.testing.assert_array_equal(
        replay.true_residual.view("<u8"), committed_r.view("<u8")
    )


def test_checkpoint_transaction_early_false_convergence_has_no_row_or_commit() -> None:
    source = _checkpoint_early_scale_source()
    replay = _checkpoint_transaction(
        source,
        solver_tolerance_l2=2.0,
        authoritative_tolerance=0.0,
        previous_false_convergence_count=3,
    )

    assert source.reduction_valid_mask == 1792
    assert replay.decision == "early_false_convergence"
    assert replay.solver_l2_passed is True
    assert replay.authoritative_linf_passed is False
    assert replay.dual_gate_passed is False
    assert replay.false_convergence_count == 4
    assert replay.commit_required is False
    assert replay.row_appended is False
    assert replay.continuation_kind == "same_cycle"
    assert replay.start_reduction_valid_mask == 1792
    assert replay.decide_reduction_valid_mask == 1792
    assert replay.commit_reduction_valid_mask == 1792
    assert replay.finalize_reduction_valid_mask == 0


def test_checkpoint_transaction_planned_bit0_dual_fail_does_not_count_false_convergence() -> (
    None
):
    residual = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=2.0,
        cycle_width=1,
        committed_solution=[0.5, 0.0],
        reduced_load=[1.0, 0.5],
    )
    assert residual.candidate_reason_bits == (1 << 0) | (1 << 2)
    source = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=residual,
        solver_tolerance_l2=2.0,
        authoritative_tolerance=0.0,
        rhs_linf=1.0,
        initial_residual_l2=0.5,
        divergence_factor=2.0,
        committed_solution=[0.5, 0.0],
    )

    replay = _checkpoint_transaction(
        source,
        solver_tolerance_l2=2.0,
        authoritative_tolerance=0.0,
        previous_false_convergence_count=7,
    )

    assert replay.planned_cycle_end is True
    assert replay.solver_l2_passed is True
    assert replay.authoritative_linf_passed is False
    assert replay.dual_gate_passed is False
    assert replay.commit_required is True
    assert replay.row_appended is True
    assert replay.false_convergence_count == 7


def test_checkpoint_transaction_dual_equality_happy_uses_h_only_flag() -> None:
    source = _checkpoint_invariant_scale_source(
        cycle_width=1,
        solver_tolerance_l2=0.5,
        authoritative_tolerance=0.5,
    )
    replay = _checkpoint_transaction(
        source,
        solver_tolerance_l2=0.5,
        authoritative_tolerance=0.5,
        previous_happy_breakdown_count=2,
    )

    assert replay.dual_gate_passed is True
    assert replay.decision == "dual_gate_converged"
    assert replay.commit_required is True
    assert replay.terminal_status == "converged"
    assert replay.terminal_status_code == 1
    assert replay.termination_code == "converged_happy_breakdown"
    assert replay.termination_code_value == 2
    assert replay.pending_restart_hint_code == 2
    assert replay.pending_restart_flags & (1 << 3)
    assert not replay.pending_restart_flags & (1 << 4)
    assert replay.happy_breakdown_count == 3
    assert replay.solution_and_true_residual_committed is True
    assert replay.restart_record is not None
    assert replay.restart_record.flags == replay.pending_restart_flags
    np.testing.assert_array_equal(
        replay.solution_x,
        source.candidate_residual.candidate_preparation.trial_x,
    )
    np.testing.assert_array_equal(
        replay.true_residual,
        source.candidate_residual.candidate_true_residual,
    )
    assert not np.signbit(replay.solution_x).any()
    assert not np.signbit(replay.true_residual).any()


def test_checkpoint_transaction_early_and_planned_dual_codes_are_distinct() -> None:
    early = _checkpoint_transaction(
        _checkpoint_early_scale_source(),
        solver_tolerance_l2=2.0,
        authoritative_tolerance=1.0,
    )
    planned_source = _checkpoint_cycle_scale_source(
        reduced_load=[0.0, 0.5],
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
    )
    planned = _checkpoint_transaction(
        planned_source,
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
    )

    assert early.termination_code == "converged_true_residual"
    assert early.termination_code_value == 3
    assert early.pending_restart_hint == "converged_true_residual"
    assert early.pending_restart_hint_code == 3
    assert planned.termination_code == "converged_restart_true_residual"
    assert planned.termination_code_value == 4
    assert planned.pending_restart_hint == "restart_completed"
    assert planned.pending_restart_hint_code == 1
    assert early.commit_required is planned.commit_required is True


def test_checkpoint_transaction_unhappy_invariant_uses_i_only_flag() -> None:
    source = _checkpoint_invariant_scale_source(
        cycle_width=1,
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
    )
    replay = _checkpoint_transaction(source)

    assert replay.dual_gate_passed is False
    assert replay.decision == "invariant_breakdown"
    assert replay.commit_required is True
    assert replay.terminal_status == "arnoldi_breakdown"
    assert replay.termination_code == "arnoldi_invariant_subspace_breakdown"
    assert replay.termination_code_value == 31
    assert replay.pending_restart_hint_code == 4
    assert replay.pending_restart_flags & (1 << 4)
    assert not replay.pending_restart_flags & (1 << 3)
    assert replay.restart_record is not None
    assert replay.restart_record.flags & (1 << 0)


def test_checkpoint_transaction_divergence_strict_equality_nextafter_and_infinity() -> (
    None
):
    equality_source = _checkpoint_cycle_scale_source(
        reduced_load=[1.0, 0.5],
        initial_residual_l2=0.5,
        divergence_factor=2.0,
    )
    equality = _checkpoint_transaction(equality_source)
    assert equality.divergence_threshold_l2 == 1.0
    assert equality.divergence_detected is False
    assert equality.decision != "diverged"

    above = float(np.nextafter(np.float64(1.0), np.float64(math.inf)))
    diverged_source = _checkpoint_cycle_scale_source(
        reduced_load=[above, 0.5],
        initial_residual_l2=0.5,
        divergence_factor=2.0,
    )
    diverged = _checkpoint_transaction(diverged_source, max_iterations=1)
    assert diverged.divergence_threshold_l2 == 1.0
    assert diverged.divergence_detected is True
    assert diverged.decision == "diverged"
    assert diverged.terminal_status == "diverged"
    assert diverged.terminal_status_code == 4
    assert diverged.termination_code_value == 21
    assert diverged.pending_restart_flags & (1 << 7)
    assert diverged.commit_required is True

    maximum = float(np.finfo(np.float64).max)
    infinite_source = _checkpoint_cycle_scale_source(
        reduced_load=[1.0, 0.5],
        initial_residual_l2=maximum,
        divergence_factor=2.0,
    )
    infinite = _checkpoint_transaction(
        infinite_source,
        initial_residual_l2=maximum,
    )
    assert infinite.divergence_threshold_l2 == math.inf
    assert infinite.divergence_detected is False
    assert infinite.decision != "diverged"


def test_checkpoint_transaction_plateau_and_tiny_boundaries_are_inclusive() -> None:
    source, committed = _checkpoint_tiny_equality_scale_source()
    replay = _checkpoint_transaction(
        source,
        committed_solution=committed,
        rhs_linf=(
            float(source.candidate_residual.candidate_preparation.trial_x[0]) + 1.0
        ),
        initial_residual_l2=1.0,
        previous_checkpoint_l2=2.0,
        previous_solution_scale_l2=3.0,
        stagnation_relative_tolerance=0.5,
        previous_stagnation_checkpoint_count=0,
        max_iterations=2,
    )

    assert replay.x_scale_l2 == math.ldexp(1.0, 26)
    assert source.solution_update_l2 is not None
    assert source.solution_update_l2.value == 1.0
    assert replay.stagnation_plateau is True
    assert replay.tiny_update is True
    assert replay.stagnation_checkpoint_count == 1
    assert replay.solution_scale_l2 == replay.x_scale_l2
    assert replay.previous_checkpoint_l2 == 1.0
    assert replay.pending_restart_flags & (1 << 5)
    assert replay.pending_restart_flags & (1 << 6)


def test_checkpoint_transaction_stagnation_streak_reset_limit_and_max_priority() -> (
    None
):
    ordinary = _checkpoint_cycle_scale_source()
    reset = _checkpoint_transaction(
        ordinary,
        previous_checkpoint_l2=3.0,
        previous_stagnation_checkpoint_count=1,
        max_iterations=2,
    )
    assert reset.stagnation_plateau is False
    assert reset.tiny_update is True
    assert reset.stagnation_checkpoint_count == 0
    assert reset.decision == "between_restarts"
    assert reset.continuation_kind == "between_restarts"

    equality_source, committed = _checkpoint_tiny_equality_scale_source()
    stagnated = _checkpoint_transaction(
        equality_source,
        committed_solution=committed,
        rhs_linf=(
            float(equality_source.candidate_residual.candidate_preparation.trial_x[0])
            + 1.0
        ),
        initial_residual_l2=1.0,
        previous_checkpoint_l2=2.0,
        stagnation_relative_tolerance=0.5,
        previous_stagnation_checkpoint_count=1,
        stagnation_checkpoint_limit=2,
        max_iterations=1,
    )
    assert stagnated.stagnation_checkpoint_count == 2
    assert stagnated.decision == "stagnated"
    assert stagnated.terminal_status == "stagnated"
    assert stagnated.terminal_status_code == 3
    assert stagnated.termination_code_value == 20

    maximum = _checkpoint_transaction(
        ordinary,
        previous_checkpoint_l2=3.0,
        previous_stagnation_checkpoint_count=0,
        max_iterations=1,
    )
    assert maximum.stagnation_checkpoint_count == 0
    assert maximum.decision == "max_iterations"
    assert maximum.terminal_status == "max_iterations"
    assert maximum.terminal_status_code == 2
    assert maximum.termination_code_value == 10


def test_checkpoint_transaction_x_scale_overflow_is_precommit_fail_closed() -> None:
    maximum = float(np.finfo(np.float64).max)
    reciprocal = 1.0 / maximum
    residual = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[reciprocal, reciprocal],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=[maximum, 0.0],
        reduced_load=[1.0, 1.0],
    )
    source = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=residual,
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
        rhs_linf=1.0,
        initial_residual_l2=maximum,
        divergence_factor=2.0,
        committed_solution=[maximum, 0.0],
    )
    assert source.trial_x_l2 is not None and source.trial_x_l2.value == maximum
    assert source.committed_x_l2 is not None
    assert source.committed_x_l2.value == maximum

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
        _checkpoint_transaction(
            source,
            committed_solution=[maximum, 0.0],
            initial_residual_l2=maximum,
        )
    assert error.value.code == "fgmres_gpu_tree_checkpoint_x_scale_overflow"
    assert error.value.path == "/x_scale_l2"


def test_checkpoint_transaction_rejects_source_and_committed_state_forgery() -> None:
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as source_type:
        _checkpoint_transaction(object())  # type: ignore[arg-type]
    assert source_type.value.code == (
        "fgmres_gpu_tree_checkpoint_transaction_source_type_invalid"
    )

    forged = replace(
        _checkpoint_cycle_scale_source(),
        reduction_valid_mask=1792,
    )
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as source_state:
        _checkpoint_transaction(forged)
    assert source_state.value.code == (
        "fgmres_gpu_tree_checkpoint_transaction_source_state_invalid"
    )

    with pytest.raises(FgmresGpuTreeReferenceV2Error) as shape:
        _checkpoint_transaction(
            _checkpoint_cycle_scale_source(),
            committed_true_residual=[1.0],
        )
    assert shape.value.code == "fgmres_gpu_tree_checkpoint_committed_shape_mismatch"


@pytest.mark.parametrize(
    ("overrides", "code"),
    (
        (
            {"previous_stagnation_checkpoint_count": -1},
            "fgmres_gpu_tree_checkpoint_counter_invalid",
        ),
        (
            {"previous_false_convergence_count": object()},
            "fgmres_gpu_tree_checkpoint_counter_invalid",
        ),
        (
            {"stagnation_relative_tolerance": 1.0},
            "fgmres_gpu_tree_checkpoint_stagnation_relative_tolerance_invalid",
        ),
        (
            {"stagnation_checkpoint_limit": 1},
            "fgmres_gpu_tree_checkpoint_stagnation_limit_invalid",
        ),
        (
            {"max_iterations": 0},
            "fgmres_gpu_tree_checkpoint_max_iterations_invalid",
        ),
        (
            {"committed_true_residual": [math.nan, 0.0]},
            "fgmres_gpu_tree_vector_nonfinite",
        ),
    ),
)
def test_checkpoint_transaction_rejects_invalid_history_policy_and_state_inputs(
    overrides: dict[str, object],
    code: str,
) -> None:
    with pytest.raises(FgmresGpuTreeReferenceV2Error) as error:
        _checkpoint_transaction(_checkpoint_cycle_scale_source(), **overrides)
    assert error.value.code == code


def test_checkpoint_transaction_raw_replay_matches_composed_oracle() -> None:
    source = _checkpoint_cycle_scale_source()
    composed = _checkpoint_transaction(source)
    raw = replay_fgmres_gpu_tree_first_column_checkpoint_transaction_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=[0.5, 0.0],
        committed_true_residual=[2.0, 0.0],
        reduced_load=[1.0, 0.5],
        authoritative_tolerance=0.0,
        rhs_linf=1.0,
        initial_residual_l2=0.5,
        divergence_factor=2.0,
        previous_checkpoint_l2=2.0,
        previous_solution_scale_l2=0.5,
        previous_stagnation_checkpoint_count=0,
        previous_false_convergence_count=0,
        previous_happy_breakdown_count=0,
        stagnation_relative_tolerance=0.1,
        stagnation_checkpoint_limit=2,
        max_iterations=2,
    )

    assert raw.decision == composed.decision
    assert raw.start_reduction_valid_mask == composed.start_reduction_valid_mask
    assert raw.finalize_reduction_valid_mask == composed.finalize_reduction_valid_mask
    assert raw.terminal_status == composed.terminal_status
    assert raw.termination_code == composed.termination_code
    assert raw.restart_record == composed.restart_record
    np.testing.assert_array_equal(raw.solution_x, composed.solution_x)
    np.testing.assert_array_equal(raw.true_residual, composed.true_residual)
    assert raw.checkpoint_decision_included is True
    assert raw.checkpoint_commit_included is True
    assert raw.checkpoint_finalize_included is True
    assert raw.restart_record is not None
    assert not raw.solution_x.flags.writeable
    assert not raw.true_residual.flags.writeable


def _candidate_identity_through_givens() -> (
    FgmresGpuTreeFirstArnoldiColumnThroughGivensReplayV2
):
    return replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 1],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=2,
    )


def _cycle_end_candidate_residual(
    *,
    committed_solution: object = (0.5, 0.0),
    reduced_load: object = (1.0, 0.5),
) -> FgmresGpuTreeFirstColumnCandidateResidualReplayV2:
    replay = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=committed_solution,
        reduced_load=reduced_load,
    )
    assert replay.candidate_reason_bits == 1 << 2
    assert replay.invariant_breakdown is False
    assert replay.candidate_replay_valid is True
    return replay


def _invariant_cycle_candidate_residual() -> (
    FgmresGpuTreeFirstColumnCandidateResidualReplayV2
):
    replay = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 1],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=[0.5, 0.0],
        reduced_load=[3.0, 0.0],
    )
    assert replay.candidate_reason_bits == 0b111
    assert replay.invariant_breakdown is True
    assert replay.candidate_replay_valid is True
    return replay


def _active_candidate_preparation(
    *, committed_solution: object
) -> FgmresGpuTreeFirstColumnCandidatePreparationV2:
    return prepare_fgmres_gpu_tree_first_column_candidate_v2(
        through_givens=_candidate_identity_through_givens(),
        committed_solution=committed_solution,
    )


def _candidate_false_preparation() -> FgmresGpuTreeFirstColumnCandidatePreparationV2:
    through = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=2,
    )
    assert through.candidate_required is False
    return prepare_fgmres_gpu_tree_first_column_candidate_v2(
        through_givens=through,
        committed_solution=object(),
    )


def _triangular_breakdown_preparation() -> (
    FgmresGpuTreeFirstColumnCandidatePreparationV2
):
    through = replay_fgmres_gpu_tree_first_arnoldi_column_through_givens_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
    )
    preparation = prepare_fgmres_gpu_tree_first_column_candidate_v2(
        through_givens=replace(through, rotated_h00=0.0),
        committed_solution=object(),
    )
    assert preparation.triangular_breakdown is True
    return preparation


def _checkpoint_inactive_scale_source() -> (
    FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2
):
    residual = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=_candidate_false_preparation(),
        row_ptr=object(),
        column_indices=object(),
        values=object(),
        reduced_load=object(),
    )
    return prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=residual,
        solver_tolerance_l2=object(),  # type: ignore[arg-type]
        authoritative_tolerance=object(),  # type: ignore[arg-type]
        rhs_linf=object(),  # type: ignore[arg-type]
        initial_residual_l2=object(),  # type: ignore[arg-type]
        divergence_factor=object(),  # type: ignore[arg-type]
        committed_solution=object(),
    )


def _checkpoint_triangular_scale_source() -> (
    FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2
):
    residual = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=_triangular_breakdown_preparation(),
        row_ptr=object(),
        column_indices=object(),
        values=object(),
        reduced_load=object(),
    )
    return prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=residual,
        solver_tolerance_l2=object(),  # type: ignore[arg-type]
        authoritative_tolerance=object(),  # type: ignore[arg-type]
        rhs_linf=object(),  # type: ignore[arg-type]
        initial_residual_l2=object(),  # type: ignore[arg-type]
        divergence_factor=object(),  # type: ignore[arg-type]
        committed_solution=object(),
    )


def _checkpoint_early_scale_source() -> (
    FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2
):
    residual = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=[0, 1, 2],
        column_indices=[1, 0],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=2.0,
        cycle_width=2,
        committed_solution=[0.5, 0.0],
        reduced_load=[1.0, 0.5],
    )
    assert residual.candidate_reason_bits == 1 << 0
    return prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=residual,
        solver_tolerance_l2=object(),  # type: ignore[arg-type]
        authoritative_tolerance=object(),  # type: ignore[arg-type]
        rhs_linf=object(),  # type: ignore[arg-type]
        initial_residual_l2=object(),  # type: ignore[arg-type]
        divergence_factor=object(),  # type: ignore[arg-type]
        committed_solution=object(),
    )


def _checkpoint_cycle_scale_source(
    *,
    reduced_load: object = (1.0, 0.5),
    solver_tolerance_l2: float = 0.0,
    authoritative_tolerance: float = 0.0,
    rhs_linf: float = 1.0,
    initial_residual_l2: float = 0.5,
    divergence_factor: float = 2.0,
) -> FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2:
    residual = _cycle_end_candidate_residual(reduced_load=reduced_load)
    return prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=residual,
        solver_tolerance_l2=solver_tolerance_l2,
        authoritative_tolerance=authoritative_tolerance,
        rhs_linf=rhs_linf,
        initial_residual_l2=initial_residual_l2,
        divergence_factor=divergence_factor,
        committed_solution=[0.5, 0.0],
    )


def _checkpoint_invariant_scale_source(
    *,
    cycle_width: int,
    solver_tolerance_l2: float,
    authoritative_tolerance: float,
) -> FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2:
    residual = replay_fgmres_gpu_tree_first_column_candidate_residual_v2(
        row_ptr=[0, 1, 2],
        column_indices=[0, 1],
        values=[1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=cycle_width,
        committed_solution=[0.5, 0.0],
        reduced_load=[3.0, 0.0],
    )
    return prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=residual,
        solver_tolerance_l2=solver_tolerance_l2,
        authoritative_tolerance=authoritative_tolerance,
        rhs_linf=1.0,
        initial_residual_l2=0.5,
        divergence_factor=2.0,
        committed_solution=[0.5, 0.0],
    )


def _checkpoint_tiny_equality_scale_source() -> tuple[
    FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2, np.ndarray
]:
    committed_value = (math.ldexp(1.0, 26) - 1.0) / 2.0
    committed = np.array([committed_value, 0.0], dtype="<f8")
    preparation = replay_fgmres_gpu_tree_first_column_candidate_preparation_v2(
        row_ptr=[0, 1, 3],
        column_indices=[0, 0, 1],
        values=[1.0, 1.0, 1.0],
        basis_v0=[1.0, 0.0],
        jacobi_inverse=[1.0, 1.0],
        cycle_beta=2.0,
        solver_tolerance_l2=0.0,
        cycle_width=1,
        committed_solution=committed,
    )
    assert preparation.trial_x is not None
    trial_value = float(preparation.trial_x[0])
    residual = prepare_fgmres_gpu_tree_first_column_candidate_residual_v2(
        candidate_preparation=preparation,
        row_ptr=[0, 1, 3],
        column_indices=[0, 0, 1],
        values=[1.0, 1.0, 1.0],
        reduced_load=[trial_value + 1.0, trial_value],
    )
    source = prepare_fgmres_gpu_tree_first_column_candidate_scale_metrics_v2(
        candidate_residual=residual,
        solver_tolerance_l2=0.0,
        authoritative_tolerance=0.0,
        rhs_linf=trial_value + 1.0,
        initial_residual_l2=1.0,
        divergence_factor=2.0,
        committed_solution=committed,
    )
    return source, committed


def _checkpoint_transaction(
    source: FgmresGpuTreeFirstColumnCandidateScaleMetricsReplayV2,
    **overrides: object,
) -> FgmresGpuTreeFirstColumnCheckpointTransactionReplayV2:
    arguments: dict[str, object] = {
        "candidate_scale_metrics": source,
        "solver_tolerance_l2": 0.0,
        "authoritative_tolerance": 0.0,
        "rhs_linf": 1.0,
        "initial_residual_l2": 0.5,
        "divergence_factor": 2.0,
        "committed_solution": [0.5, 0.0],
        "committed_true_residual": [2.0, 0.0],
        "previous_checkpoint_l2": 2.0,
        "previous_solution_scale_l2": 0.5,
        "previous_stagnation_checkpoint_count": 0,
        "previous_false_convergence_count": 0,
        "previous_happy_breakdown_count": 0,
        "stagnation_relative_tolerance": 0.1,
        "stagnation_checkpoint_limit": 2,
        "max_iterations": 2,
    }
    arguments.update(overrides)
    return prepare_fgmres_gpu_tree_first_column_checkpoint_transaction_v2(
        **arguments,  # type: ignore[arg-type]
    )


def _assert_replay_arrays_immutable_and_canonical(replay: object) -> None:
    for name in (
        "basis_v0",
        "jacobi_z0",
        "operator_work",
        "work_after_first",
        "work_after_final",
        "basis_v1",
    ):
        array = getattr(replay, name)
        assert array.dtype == np.dtype("<f8")
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        for value in array:
            if float(value) == 0.0:
                assert math.copysign(1.0, float(value)) == 1.0
