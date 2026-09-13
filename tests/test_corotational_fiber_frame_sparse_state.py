"""Small assembly-only storage/state tests; no Newton or benchmark workloads."""

from __future__ import annotations

from copy import copy
from dataclasses import replace

import numpy as np
import pytest
from scipy.sparse import coo_matrix, csc_matrix, csr_matrix

from structural_analysis.assembly import (
    stateful_corotational_fiber_frame2d as dense_module,
)
from structural_analysis.assembly import (
    stateful_corotational_fiber_frame2d_sparse as native_module,
)
from structural_analysis.assembly import (
    stateful_corotational_fiber_frame2d_sparse_state as sparse_module,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_sparse_state import (
    COROTATIONAL_FIBER_FRAME_SPARSE_STATE_STORAGE_PROFILE,
    CorotationalFiberFrameCSR,
    assemble_stateful_corotational_fiber_frame2d_sparse_state,
    validate_stateful_corotational_fiber_frame2d_sparse_assembly,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)
from tests.test_corotational_fiber_frame_sparse import _portal_problem

TRIAL = np.asarray([1e-4, -2e-5, -4e-5, 1.2e-4, -2.1e-5, -4.5e-5])


def _input(prescribed=False):
    problem = _portal_problem()
    if prescribed:
        problem = replace(problem, prescribed_displacements=((3, 2e-4),))
    return problem, initial_stateful_corotational_fiber_frame2d_checkpoint(problem)


@pytest.fixture(
    scope="module", params=[False, True], ids=["unforced-support", "prescribed-support"]
)
def assemblies(request):
    problem, checkpoint = _input(request.param)
    checkpoint_bytes = checkpoint.canonical_bytes()
    kwargs = dict(target_load_factor=0.75, trial_free_coordinates_m=TRIAL)
    dense = assemble_stateful_corotational_fiber_frame2d(problem, checkpoint, **kwargs)
    sparse = assemble_stateful_corotational_fiber_frame2d_sparse_state(
        problem, checkpoint, **kwargs
    )
    return problem, checkpoint, checkpoint_bytes, dense, sparse


def test_full_sparse_state_retains_physical_vectors_member_rows_and_states(assemblies):
    problem, checkpoint, original, dense, sparse = assemblies
    assert (
        sparse.storage_profile == COROTATIONAL_FIBER_FRAME_SPARSE_STATE_STORAGE_PROFILE
    )
    assert (
        validate_stateful_corotational_fiber_frame2d_sparse_assembly(
            sparse, problem=problem, checkpoint=checkpoint
        )
        is sparse
    )
    assert sparse.free_global_dofs == dense.free_global_dofs
    for name in sparse_module._VECTOR_NAMES:
        np.testing.assert_allclose(
            getattr(sparse, name), getattr(dense, name), rtol=1e-13, atol=1e-10
        )
    assert [row.to_dict() for row in sparse.member_assemblies] == [
        row.to_dict() for row in dense.member_assemblies
    ]
    assert [state.canonical_bytes() for state in sparse.trial_element_states] == [
        state.canonical_bytes() for state in dense.trial_element_states
    ]
    assert checkpoint.canonical_bytes() == original
    exported = sparse.to_dict()
    assert "jacobian_kn_per_m" not in exported
    assert "consistent_tangent_global" not in exported
    assert exported["assembly_hash"] == canonical_hash(
        {k: v for k, v in exported.items() if k != "assembly_hash"}
    )
    for csr_name, dense_name in (
        ("jacobian_csr", "jacobian_kn_per_m"),
        ("material_tangent_global_csr", "material_tangent_global"),
        ("geometric_tangent_global_csr", "geometric_tangent_global"),
        ("consistent_tangent_global_csr", "consistent_tangent_global"),
    ):
        matrix = getattr(sparse, csr_name)
        assert matrix.has_canonical_format
        np.testing.assert_allclose(
            matrix.toarray(), getattr(dense, dense_name), rtol=1e-13, atol=1e-10
        )


@pytest.mark.parametrize(
    ("prescribed", "expected_hash"),
    [
        (
            False,
            "sha256:7839cd67fc2b1e980395b672af8589c7fac49065f8525ac2c0fa7fd18e37f6b4",
        ),
        (
            True,
            "sha256:0c238e1c373faa56aca66479b48661b86975a9a5e6eacc8becc8d862e6b5dfc5",
        ),
    ],
)
def test_newton_v1_full_manifest_is_unchanged_from_pre_refactor(
    prescribed, expected_hash
):
    # Captured from this exact portal/input before extracting the shared loop.
    problem, checkpoint = _input(prescribed)
    native = native_module.assemble_stateful_corotational_fiber_frame2d_sparse(
        problem, checkpoint, target_load_factor=0.75, trial_free_coordinates_m=TRIAL
    )
    assert canonical_hash(native.to_manifest()) == expected_hash


def test_full_state_manifest_is_exactly_unchanged_by_validation_reuse(assemblies):
    problem, _, _, _, sparse = assemblies
    # Full serialized manifests captured before validation reuse, from these
    # exact inputs. This also binds every nested CSR/member/state hash and row.
    expected = (
        "sha256:d7257980d068a7d7b67d2f05712a5fe70ad28952ed8485aa8933b197cb7c67f3"
        if problem.prescribed_displacements
        else "sha256:ecb91782ac1af649db1e788622c266f4d1ba2425789b3e62aa31664a78d065b7"
    )
    assert canonical_hash(sparse.to_dict()) == expected


def test_each_public_export_checks_every_csr_once_and_returns_fresh_data(
    assemblies, monkeypatch
):
    *_, sparse = assemblies
    validate_csr = sparse_module._validate_csr
    calls = []

    def counted(matrix, *, hashes=True):
        calls.append((id(matrix), hashes))
        return validate_csr(matrix, hashes=hashes)

    monkeypatch.setattr(sparse_module, "_validate_csr", counted)
    original = sparse.to_dict()
    expected_calls = [
        (id(getattr(sparse, name)), True) for name in sparse_module._MATRIX_NAMES
    ]
    assert calls == expected_calls
    first = sparse.to_dict()
    assert calls == expected_calls * 2
    first["jacobian_csr"]["values"][0] += 1.0
    first["member_assemblies"].clear()
    assert sparse.to_dict() == original
    assert calls == expected_calls * 3


def test_csr_vectors_and_exports_cannot_mutate_the_stored_artifact(assemblies):
    *_, sparse = assemblies
    original = sparse.to_dict()
    for name in sparse_module._VECTOR_NAMES:
        with pytest.raises(ValueError):
            getattr(sparse, name).setflags(write=True)
    for name in sparse_module._MATRIX_NAMES:
        matrix = getattr(sparse, name)
        for array in (matrix.row_ptr, matrix.column_indices, matrix.values):
            with pytest.raises(ValueError):
                array.setflags(write=True)
        detached = matrix.to_csr()
        if detached.nnz:
            detached.data[0] += 1000.0
        detached.indptr[:] = 0
    exported = sparse.to_dict()
    exported["jacobian_csr"]["values"][0] += 1000.0
    exported["global_displacements"][0] = 42.0
    assert sparse.to_dict() == original


def test_full_state_and_validation_integrate_each_member_once_without_global_dense(
    monkeypatch,
):
    problem, checkpoint = _input(True)
    integrate = native_module.integrate_corotational_frame2d_member_features
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[0].element_id)
        return integrate(*args, **kwargs)

    def denied(*args, **kwargs):
        raise AssertionError("global dense assembly/conversion was used")

    monkeypatch.setattr(
        native_module, "integrate_corotational_frame2d_member_features", counted
    )
    monkeypatch.setattr(
        native_module, "assemble_stateful_corotational_fiber_frame2d", denied
    )
    monkeypatch.setattr(
        dense_module, "assemble_stateful_corotational_fiber_frame2d", denied
    )
    for matrix_type in (csr_matrix, coo_matrix, csc_matrix):
        monkeypatch.setattr(matrix_type, "toarray", denied)
        monkeypatch.setattr(matrix_type, "todense", denied)
    for name in ("zeros", "empty", "ones", "full"):
        original = getattr(np, name)

        def bounded(shape, *args, _original=original, **kwargs):
            if isinstance(shape, tuple) and len(shape) == 2 and min(shape) > 6:
                raise AssertionError("global quadratic ndarray was allocated")
            return _original(shape, *args, **kwargs)

        monkeypatch.setattr(np, name, bounded)
    sparse = assemble_stateful_corotational_fiber_frame2d_sparse_state(
        problem, checkpoint, target_load_factor=0.75, trial_free_coordinates_m=TRIAL
    )
    sparse.to_dict()
    validate_stateful_corotational_fiber_frame2d_sparse_assembly(sparse)
    assert calls == [member.element.element_id for member in problem.members]


def test_reaction_only_has_canonical_zero_by_zero_free_csr():
    problem = replace(
        _portal_problem(),
        fixed_global_dofs=tuple(range(12)),
        prescribed_displacements=((3, 2e-4),),
    )
    parent = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
    sparse = assemble_stateful_corotational_fiber_frame2d_sparse_state(
        problem, parent, target_load_factor=0.75, trial_free_coordinates_m=np.empty(0)
    )
    dense = assemble_stateful_corotational_fiber_frame2d(
        problem, parent, target_load_factor=0.75, trial_free_coordinates_m=np.empty(0)
    )
    assert sparse.jacobian.shape == (0, 0)
    assert sparse.jacobian.nnz == 0
    assert sparse.jacobian.row_ptr.tolist() == [0]
    assert (
        sparse.residual_kn.size == sparse.residual_load_factor_derivative_kn.size == 0
    )
    np.testing.assert_array_equal(sparse.reactions_global, dense.reactions_global)
    assert sparse.to_dict()["jacobian_csr"]["shape"] == [0, 0]


def test_load_derivative_includes_proportional_prescribed_displacement(assemblies):
    problem, checkpoint, _, dense, sparse = assemblies
    if not problem.prescribed_displacements:
        assert np.array_equal(
            sparse.residual_load_factor_derivative_kn,
            dense.residual_load_factor_derivative_kn,
        )
        return
    h = 1e-5
    residuals = [
        assemble_stateful_corotational_fiber_frame2d_sparse_state(
            problem,
            checkpoint,
            target_load_factor=0.75 + sign * h,
            trial_free_coordinates_m=TRIAL,
        ).residual_kn
        for sign in (-1, 1)
    ]
    finite_difference = (residuals[1] - residuals[0]) / (2 * h)
    np.testing.assert_allclose(
        sparse.residual_load_factor_derivative_kn,
        finite_difference,
        rtol=1e-6,
        atol=1e-5,
    )
    assert not np.array_equal(
        sparse.residual_load_factor_derivative_kn,
        sparse.partial_residual_load_factor_derivative_global[
            list(problem.free_global_dofs)
        ]
        * problem.physical_coordinate_scale[list(problem.free_global_dofs)],
    )


@pytest.mark.parametrize("field", sparse_module._VECTOR_NAMES)
def test_mutable_or_nonfinite_stored_vector_rejected(assemblies, field):
    *_, sparse = assemblies
    with pytest.raises(ValueError, match="immutable"):
        replace(sparse, **{field: getattr(sparse, field).copy()})


@pytest.mark.parametrize("field", sparse_module._MATRIX_NAMES)
def test_rehashed_csr_numeric_change_is_rejected_by_member_scatter(assemblies, field):
    *_, sparse = assemblies
    matrix = getattr(sparse, field)
    changed = matrix.values.copy()
    changed[0] += 1.0
    rehashed = CorotationalFiberFrameCSR(
        matrix.shape,
        matrix.row_ptr,
        matrix.column_indices,
        immutable_array(changed, dtype="<f8"),
    )
    with pytest.raises(ValueError, match="scatter"):
        replace(sparse, **{field: rehashed})


@pytest.mark.parametrize("method", ["to_dict", "to_csr"])
@pytest.mark.parametrize("field", ["pattern_hash", "numeric_hash", "nnz"])
def test_stale_csr_metadata_is_rejected_after_successful_export(
    assemblies, field, method
):
    *_, sparse = assemblies
    changed = copy(sparse.jacobian)
    getattr(changed, method)()
    object.__setattr__(changed, field, True if field == "nnz" else "sha256:" + "f" * 64)
    with pytest.raises(ValueError, match="stale"):
        getattr(changed, method)()


@pytest.mark.parametrize("operation", ["to_dict", "validate"])
@pytest.mark.parametrize(
    "mutation", ["rehashed_csr", "member_feature", "parent_checkpoint", "source_loads"]
)
def test_each_public_call_revalidates_sources_after_prior_success(
    assemblies, operation, mutation
):
    *_, sparse = assemblies
    changed = copy(sparse)
    matrix = copy(sparse.jacobian)
    row = copy(sparse.member_assemblies[0])
    feature = copy(row.feature_response)
    parent = copy(sparse._source_checkpoint)
    problem = copy(sparse._source_problem)
    object.__setattr__(row, "feature_response", feature)
    object.__setattr__(changed, "jacobian", matrix)
    object.__setattr__(
        changed, "member_assemblies", (row, *sparse.member_assemblies[1:])
    )
    object.__setattr__(changed, "_source_checkpoint", parent)
    object.__setattr__(changed, "_source_problem", problem)

    def public_call():
        if operation == "to_dict":
            return changed.to_dict()
        return validate_stateful_corotational_fiber_frame2d_sparse_assembly(changed)

    public_call()
    if mutation == "rehashed_csr":
        values = matrix.values.copy()
        values[0] += 1.0
        object.__setattr__(
            changed,
            "jacobian",
            CorotationalFiberFrameCSR(
                matrix.shape,
                matrix.row_ptr,
                matrix.column_indices,
                immutable_array(values, dtype="<f8"),
            ),
        )
    elif mutation == "member_feature":
        object.__setattr__(feature, "response_hash", "sha256:" + "0" * 64)
    elif mutation == "parent_checkpoint":
        object.__setattr__(parent, "state_hash", "sha256:" + "f" * 64)
    elif mutation == "source_loads":
        loads = list(problem.reference_external_loads)
        dof, value = loads[0]
        loads[0] = (dof, value + 1.0)
        object.__setattr__(problem, "reference_external_loads", tuple(loads))
    # An internally rehashed export must still recheck retained source data and
    # independently scatter member tangents, rather than trust prior success.
    object.__setattr__(
        changed,
        "assembly_hash",
        canonical_hash(sparse_module._assembly_payload(changed)),
    )
    with pytest.raises(ValueError):
        public_call()


@pytest.mark.parametrize(
    "mutation",
    [
        "residual",
        "reaction",
        "assembly_hash",
        "profile",
        "free_dof",
        "member",
        "state",
        "feature_zero_hash",
    ],
)
def test_rehashed_or_detached_assembly_contract_rejected(assemblies, mutation):
    *_, sparse = assemblies
    changed = copy(sparse)
    if mutation in ("residual", "reaction"):
        field = "residual_kn" if mutation == "residual" else "reactions_global"
        values = getattr(sparse, field).copy()
        values[0] += 1.0
        object.__setattr__(changed, field, immutable_array(values, dtype="<f8"))
        object.__setattr__(
            changed,
            "assembly_hash",
            canonical_hash(sparse_module._assembly_payload(changed)),
        )
    elif mutation == "assembly_hash":
        object.__setattr__(changed, "assembly_hash", "sha256:" + "f" * 64)
    elif mutation == "profile":
        object.__setattr__(changed, "storage_profile", "numpy_dense_ndarray")
    elif mutation == "free_dof":
        object.__setattr__(
            changed, "free_global_dofs", tuple(reversed(sparse.free_global_dofs))
        )
    elif mutation == "member":
        object.__setattr__(
            changed, "member_assemblies", tuple(reversed(sparse.member_assemblies))
        )
    elif mutation == "state":
        object.__setattr__(
            changed,
            "trial_element_states",
            tuple(reversed(sparse.trial_element_states)),
        )
    elif mutation == "feature_zero_hash":
        row = sparse.member_assemblies[0]
        feature = replace(row.feature_response, response_hash="sha256:" + "0" * 64)
        object.__setattr__(
            changed,
            "member_assemblies",
            (replace(row, feature_response=feature), *sparse.member_assemblies[1:]),
        )
    with pytest.raises(ValueError):
        changed.to_dict()


def test_optional_source_arguments_cannot_detach_the_artifact(assemblies):
    problem, checkpoint, _, _, sparse = assemblies
    with pytest.raises(ValueError, match="supplied problem"):
        validate_stateful_corotational_fiber_frame2d_sparse_assembly(
            sparse, problem=replace(problem, case_id="other")
        )
    with pytest.raises(ValueError, match="supplied parent"):
        validate_stateful_corotational_fiber_frame2d_sparse_assembly(
            sparse, checkpoint=replace(checkpoint, case_id="other", state_hash="")
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "shape_bool",
        "rowptr_dtype",
        "rowptr_end",
        "rowptr_descending",
        "negative_column",
        "out_of_range_column",
        "duplicate_column",
        "unsorted_columns",
        "explicit_zero",
        "nonfinite",
        "mutable",
    ],
)
def test_csr_structure_is_strict_and_canonical(mutation):
    shape = (2, 2)
    row_ptr = np.array([0, 2, 3], dtype="<i8")
    columns = np.array([0, 1, 1], dtype="<i8")
    values = np.array([1.0, 2.0, 3.0], dtype="<f8")
    if mutation == "shape_bool":
        shape = (True, 2)
    elif mutation == "rowptr_dtype":
        row_ptr = row_ptr.astype("<f8")
    elif mutation == "rowptr_end":
        row_ptr[-1] = 4
    elif mutation == "rowptr_descending":
        row_ptr[:] = [0, 4, 3]
    elif mutation == "negative_column":
        columns[0] = -1
    elif mutation == "out_of_range_column":
        columns[0] = 2
    elif mutation == "duplicate_column":
        columns[1] = 0
    elif mutation == "unsorted_columns":
        columns[:2] = [1, 0]
    elif mutation == "explicit_zero":
        values[0] = 0
    elif mutation == "nonfinite":
        values[0] = np.inf
    row_ptr = immutable_array(row_ptr, dtype=row_ptr.dtype)
    columns = immutable_array(columns, dtype="<i8")
    if mutation == "nonfinite":
        # Deliberately supply immutable bytes that bypass the safe producer.
        values = np.frombuffer(values.tobytes(), dtype="<f8")
    elif mutation != "mutable":
        values = immutable_array(values, dtype="<f8")
    with pytest.raises(ValueError):
        CorotationalFiberFrameCSR(shape, row_ptr, columns, values)
