from __future__ import annotations

import ast
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.ai.projection import (  # noqa: E402
    MAX_PROJECTION_RANK,
    ProjectionError,
    _projection_hash,
    apply_fixed_rank_projection,
    build_fixed_rank_projection,
    validate_fixed_rank_projection,
)
from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    compile_execution_plan,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
PROJECTION_SOURCE = (
    SRC_ROOT / "structural_analysis/engine_v2/ai/projection.py"
)


def _plan(load_pattern_id: str = "LC_WEAK"):
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id=load_pattern_id
    )
    return compile_execution_plan(buffers)


def _independent_candidates(n: int) -> np.ndarray:
    first = np.linspace(1.0, 2.0, n, dtype="<f8")
    second = np.linspace(-0.5, 0.75, n, dtype="<f8")
    return np.column_stack((first, second))


def _mechanism_plan():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["sections"][0]["family_id"] = "truss_3d"
    payload["sections"][0]["parameters"] = {"area_m2": 0.02}
    element = payload["elements"][0]
    element["type"] = "truss_3d"
    element["formulation"] = "linear_truss_3d"
    element.pop("local_axis_rotation_rad")
    element.pop("releases")
    buffers = pack_solver_model_buffers(payload, load_pattern_id="LC_AXIAL")
    return compile_execution_plan(buffers)


def test_projection_is_bound_to_actual_execution_plan_jacobi_scaling() -> None:
    plan = _plan()
    n = len(plan.free_dofs)
    projection = build_fixed_rank_projection(
        plan, _independent_candidates(n), rank_cap=4
    )
    free = plan.array("free_dofs")
    stiffness = plan.array("global_stiffness_dense")
    expected_scaling = 1.0 / np.sqrt(np.diag(stiffness[np.ix_(free, free)]))

    assert projection.plan_hash == plan.plan_hash
    assert projection.operator_hash == plan.operator_hash
    assert projection.pattern_hash == plan.pattern_hash
    assert projection.free_dof_count == n
    assert projection.retained_rank == 2
    np.testing.assert_array_equal(projection.scaling_diagonal, expected_scaling)
    validate_fixed_rank_projection(projection, expected_plan=plan)

    for array in (
        projection.scaling_diagonal,
        projection.candidate_vectors,
        projection.basis_q,
    ):
        assert array.dtype.str == "<f8"
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_two_pass_mgs_and_implicit_projection_match_reference_without_dense_artifact() -> None:
    plan = _plan()
    n = len(plan.free_dofs)
    projection = build_fixed_rank_projection(
        plan, _independent_candidates(n), rank_cap=2
    )
    vector = np.linspace(-3.0, 5.0, n, dtype="<f8")

    result = projection.apply(vector)
    function_result = apply_fixed_rank_projection(projection, vector)
    # An explicit projector is allowed only here as a small test oracle.
    reference = projection.basis_q @ (projection.basis_q.T @ vector)

    np.testing.assert_allclose(result, reference, rtol=0.0, atol=1.0e-14)
    np.testing.assert_array_equal(result, function_result)
    np.testing.assert_allclose(
        projection.apply(result), result, rtol=0.0, atol=1.0e-14
    )
    assert result.dtype.str == "<f8"
    assert not result.flags.writeable
    with pytest.raises(ValueError):
        result.setflags(write=True)

    scaled = projection.scale_free_vector(vector)
    np.testing.assert_array_equal(scaled, vector / projection.scaling_diagonal)
    assert scaled.dtype.str == "<f8"
    assert not scaled.flags.writeable
    np.testing.assert_array_equal(projection.unscale_free_vector(scaled), vector)


def test_projection_receipt_records_exact_bounded_work_and_dependent_drop() -> None:
    plan = _plan()
    n = len(plan.free_dofs)
    independent = _independent_candidates(n)
    candidates = np.column_stack(
        (independent[:, 0], independent[:, 1], independent[:, 0] + independent[:, 1])
    )
    projection = build_fixed_rank_projection(plan, candidates, rank_cap=3)
    receipt = projection.complexity_receipt

    assert projection.retained_rank == 2
    assert receipt.n == n
    assert receipt.k == 2
    assert receipt.nnz == plan.array("reduced_csr_column_indices").size
    assert receipt.candidate_count == 3
    assert receipt.rank_cap == 3
    assert receipt.basis_scaling_multiply_count == n * 3
    # Retained-before-candidate ranks are 0, 1, 2; two MGS passes each.
    assert receipt.orthogonalization_dot_count == 6
    assert receipt.orthogonalization_axpy_count == 6
    assert receipt.orthogonalization_multiply_count == n * 12
    assert receipt.normalization_divide_count == n * 2
    assert receipt.multiply_count == 2 * n * 2
    assert receipt.dot_count == 2
    assert receipt.axpy_count == 2
    assert receipt.basis_elements == n * 2
    assert receipt.source_vector_elements == n * 3
    assert receipt.dense_projector_elements == 0
    assert receipt.max_dense_square_dimension == 2
    assert receipt.max_dense_square_dimension <= receipt.k
    assert receipt.projection_complexity == "O(Nk)"
    assert receipt.orthonormalization_complexity == "O(Nk^2)"
    assert projection.orthogonality_error_frobenius <= 1.0e-10
    assert projection.orthogonality_error_max_abs <= 1.0e-10

    manifest = projection.to_manifest()
    assert manifest["implementation_constraints"] == {
        "basis_construction": "deterministic_two_pass_modified_gram_schmidt",
        "projection_application": "Q(Q^T v)",
        "explicit_dense_projector": False,
        "reverse_mode_autograd": False,
    }
    assert "values" not in manifest["arrays"]["basis_q"]


def test_projection_build_is_byte_deterministic() -> None:
    plan = _plan()
    candidates = _independent_candidates(len(plan.free_dofs))
    first = build_fixed_rank_projection(plan, candidates, rank_cap=4)
    second = build_fixed_rank_projection(plan, candidates, rank_cap=4)

    assert first.projection_hash == second.projection_hash
    assert first.to_manifest() == second.to_manifest()
    np.testing.assert_array_equal(first.scaling_diagonal, second.scaling_diagonal)
    np.testing.assert_array_equal(first.candidate_vectors, second.candidate_vectors)
    np.testing.assert_array_equal(first.basis_q, second.basis_q)


def test_projection_fails_closed_on_non_positive_kff_diagonal() -> None:
    plan = _mechanism_plan()
    n = len(plan.free_dofs)
    with pytest.raises(ProjectionError) as error:
        build_fixed_rank_projection(plan, np.eye(n, 1), rank_cap=1)
    assert error.value.code == "projection_stiffness_diagonal_not_positive"


@pytest.mark.parametrize("rank_cap", [0, 17, True, 1.5])
def test_projection_rejects_invalid_rank_caps(rank_cap: object) -> None:
    plan = _plan()
    with pytest.raises(ProjectionError) as error:
        build_fixed_rank_projection(
            plan,
            np.eye(len(plan.free_dofs), 1),
            rank_cap=rank_cap,  # type: ignore[arg-type]
        )
    assert error.value.code == "projection_rank_cap_invalid"


def test_projection_rejects_unbounded_candidates_and_zero_rank() -> None:
    plan = _plan()
    n = len(plan.free_dofs)
    with pytest.raises(ProjectionError) as error:
        build_fixed_rank_projection(
            plan,
            np.ones((n, MAX_PROJECTION_RANK + 1)),
            rank_cap=MAX_PROJECTION_RANK,
        )
    assert error.value.code == "projection_candidate_count_exceeds_rank_cap"

    with pytest.raises(ProjectionError) as error:
        build_fixed_rank_projection(plan, np.zeros((n, 2)), rank_cap=2)
    assert error.value.code == "projection_basis_rank_zero"


def test_projection_rejects_non_finite_candidates_and_application_vectors() -> None:
    plan = _plan()
    n = len(plan.free_dofs)
    candidates = _independent_candidates(n)
    candidates[0, 0] = np.inf
    with pytest.raises(ProjectionError) as error:
        build_fixed_rank_projection(plan, candidates, rank_cap=2)
    assert error.value.code == "projection_candidate_non_finite"

    projection = build_fixed_rank_projection(
        plan, _independent_candidates(n), rank_cap=2
    )
    vector = np.zeros(n)
    vector[-1] = np.nan
    with pytest.raises(ProjectionError) as error:
        projection.apply(vector)
    assert error.value.code == "projection_vector_non_finite"


def test_projection_rejects_basis_candidate_and_complexity_tampering() -> None:
    plan = _plan()
    projection = build_fixed_rank_projection(
        plan, _independent_candidates(len(plan.free_dofs)), rank_cap=2
    )

    basis = projection.basis_q.copy()
    basis[0, 0] += 1.0e-6
    forged_basis = replace(
        projection, basis_q=immutable_array(basis, dtype="<f8")
    )
    with pytest.raises(ProjectionError) as error:
        validate_fixed_rank_projection(forged_basis)
    assert error.value.code == "projection_basis_replay_mismatch"

    candidates = projection.candidate_vectors.copy()
    candidates[-1, -1] += 1.0
    forged_candidates = replace(
        projection,
        candidate_vectors=immutable_array(candidates, dtype="<f8"),
    )
    with pytest.raises(ProjectionError) as error:
        validate_fixed_rank_projection(forged_candidates)
    assert error.value.code == "projection_basis_replay_mismatch"

    forged_receipt = replace(
        projection.complexity_receipt,
        multiply_count=projection.complexity_receipt.multiply_count + 1,
    )
    with pytest.raises(ProjectionError) as error:
        validate_fixed_rank_projection(
            replace(projection, complexity_receipt=forged_receipt),
            expected_plan=plan,
        )
    assert error.value.code == "projection_complexity_receipt_mismatch"


def test_projection_rejects_rehashed_scaling_tamper_against_plan() -> None:
    plan = _plan()
    projection = build_fixed_rank_projection(
        plan, _independent_candidates(len(plan.free_dofs)), rank_cap=2
    )
    scaling = projection.scaling_diagonal.copy()
    scaling[0] *= 1.01
    provisional = replace(
        projection,
        scaling_diagonal=immutable_array(scaling, dtype="<f8"),
    )
    forged = replace(provisional, projection_hash=_projection_hash(provisional))

    with pytest.raises(ProjectionError) as error:
        validate_fixed_rank_projection(forged, expected_plan=plan)
    assert error.value.code == "projection_scaling_plan_mismatch"


def test_projection_rejects_different_execution_plan_binding() -> None:
    plan = _plan("LC_WEAK")
    other_plan = _plan("LC_STRONG")
    projection = build_fixed_rank_projection(
        plan, _independent_candidates(len(plan.free_dofs)), rank_cap=2
    )

    with pytest.raises(ProjectionError) as error:
        validate_fixed_rank_projection(projection, expected_plan=other_plan)
    assert error.value.code == "projection_plan_binding_mismatch"


def test_projection_module_has_no_ml_framework_or_legacy_imports() -> None:
    tree = ast.parse(PROJECTION_SOURCE.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert not imported_roots.intersection(
        {"torch", "jax", "tensorflow", "autograd"}
    )
    source = PROJECTION_SOURCE.read_text(encoding="utf-8")
    assert "implementation.phase1" not in source
    assert "structural_analysis.ai" not in source
