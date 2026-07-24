from pathlib import Path

source_path = Path("src/structural_analysis/solvers/nonlinear/sparse_factorization.py")
source = source_path.read_text(encoding="utf-8")

replacements = [
    (
        '''        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be a non-empty string")
''',
        '''        if self.policy_id != SPARSE_FACTORIZATION_POLICY_ID:
            raise ValueError(
                "policy_id must equal " + SPARSE_FACTORIZATION_POLICY_ID
            )
''',
    ),
    (
        '''    condition_number_1 = matrix_norm_1 * inverse_norm_1
    residual = np.asarray(csr @ solution - vector, dtype=np.float64)
''',
        '''    condition_number_1 = matrix_norm_1 * inverse_norm_1
    if not math.isfinite(condition_number_1):
        raise SparseFactorizationError(
            "sparse_condition_number_nonfinite",
            "exact condition-number calculation returned a non-finite value",
        )
    residual = np.asarray(csr @ solution - vector, dtype=np.float64)
''',
    ),
    (
        '''    checks = normalized["checks"]
    expected_quality_checks = {
''',
        '''    pivot_minimum = float(normalized["absolute_pivot_minimum"])
    pivot_maximum = float(normalized["absolute_pivot_maximum"])
    if pivot_minimum > pivot_maximum:
        raise ValueError("sparse factorization diagnostic pivot extrema mismatch")
    expected_normalized_pivot = (
        pivot_minimum / pivot_maximum if pivot_maximum > 0.0 else 0.0
    )
    if not math.isclose(
        float(normalized["normalized_absolute_pivot_minimum"]),
        expected_normalized_pivot,
        rel_tol=1.0e-15,
        abs_tol=0.0,
    ):
        raise ValueError("sparse factorization diagnostic pivot ratio mismatch")

    checks = normalized["checks"]
    expected_quality_checks = {
''',
    ),
    (
        '''def _canonical_csr(matrix: Any) -> csr_matrix:
    csr = (
        matrix.tocsr(copy=True)
        if issparse(matrix)
        else csr_matrix(np.asarray(matrix, dtype=np.float64))
    )
    csr.sum_duplicates()
''',
        '''def _canonical_csr(matrix: Any) -> csr_matrix:
    if issparse(matrix):
        if np.iscomplexobj(matrix.data):
            raise SparseFactorizationError(
                "sparse_factorization_matrix_complex",
                "matrix must be real-valued",
            )
        csr = matrix.tocsr(copy=True)
    else:
        dense = np.asarray(matrix)
        if np.iscomplexobj(dense):
            raise SparseFactorizationError(
                "sparse_factorization_matrix_complex",
                "matrix must be real-valued",
            )
        csr = csr_matrix(np.asarray(dense, dtype=np.float64))
    csr.sum_duplicates()
''',
    ),
]
for old, new in replacements:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"source replacement count was {count} instead of 1")
    source = source.replace(old, new)
source_path.write_text(source, encoding="utf-8")

test_path = Path("tests/test_sparse_factorization_diagnostics.py")
tests = test_path.read_text(encoding="utf-8")
old_import = '''from copy import deepcopy
from dataclasses import replace

import numpy as np
'''
new_import = '''from copy import deepcopy
from dataclasses import replace
import math

import numpy as np
'''
if tests.count(old_import) != 1:
    raise SystemExit("test import replacement did not match exactly once")
tests = tests.replace(old_import, new_import)

old_sparse_import = '''from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.sparse_factorization import (
'''
new_sparse_import = '''from structural_analysis.engine_v2.contracts._canonical import canonical_hash
import structural_analysis.solvers.nonlinear.sparse_factorization as sparse_factorization
from structural_analysis.solvers.nonlinear.sparse_factorization import (
'''
if tests.count(old_sparse_import) != 1:
    raise SystemExit("test module import replacement did not match exactly once")
tests = tests.replace(old_sparse_import, new_sparse_import)

marker = '''def test_singular_matrix_and_diagnostic_scope_fail_closed() -> None:
'''
additions = '''def test_policy_id_must_match_the_packaged_public_schema() -> None:
    with pytest.raises(ValueError, match="policy_id must equal"):
        SparseFactorizationPolicy(policy_id="custom-policy.v1")


def test_complex_sparse_tangent_is_rejected_before_factorization() -> None:
    matrix = csr_matrix(np.diag([1.0 + 1.0e-16j, 2.0 + 0.0j]))

    with pytest.raises(
        SparseFactorizationError,
        match="sparse_factorization_matrix_complex",
    ):
        factorize_and_solve_sparse(matrix, [1.0, 1.0])


def test_nonfinite_condition_estimate_raises_structured_error(monkeypatch) -> None:
    monkeypatch.setattr(
        sparse_factorization,
        "_exact_inverse_one_norm",
        lambda _factor, _size: math.inf,
    )

    with pytest.raises(
        SparseFactorizationError,
        match="sparse_condition_number_nonfinite",
    ) as caught:
        factorize_and_solve_sparse(csr_matrix(np.eye(2)), [1.0, 1.0])

    assert caught.value.code == "sparse_condition_number_nonfinite"
    assert caught.value.diagnostic is None


def test_rehashed_pivot_relationship_tampering_is_rejected() -> None:
    manifest = factorize_and_solve_sparse(
        csr_matrix(np.asarray([[4.0, -1.0], [-1.0, 3.0]])),
        [1.0, 2.0],
    ).diagnostic.to_manifest()
    manifest["absolute_pivot_minimum"] = 0.0
    _rehash_manifest(manifest)

    with pytest.raises(ValueError, match="pivot ratio mismatch"):
        validate_sparse_factorization_diagnostic_manifest(manifest)


def test_singular_matrix_and_diagnostic_scope_fail_closed() -> None:
'''
if tests.count(marker) != 1:
    raise SystemExit("test insertion marker did not match exactly once")
tests = tests.replace(marker, additions)
test_path.write_text(tests, encoding="utf-8")
