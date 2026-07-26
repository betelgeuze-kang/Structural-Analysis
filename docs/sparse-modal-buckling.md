# Experimental sparse modal and buckling extraction

The modal and linear-buckling whole-model analyses expose opt-in sparse
low-mode extraction backends. The existing dense backends remain the defaults
and retain their bounded public status. The sparse paths are experimental and
do not expand release authority.

## Backend contracts

Modal extraction uses
`scipy_arpack_symmetric_generalized_modal.v1`. It accepts CSR stiffness and
mass matrices, verifies symmetry, positive definiteness of mass, and positive
semidefiniteness of stiffness, then extracts a bounded low-mode subspace with
ARPACK `eigsh`. Rigid modes are excluded without diagonal regularization.

Linear buckling uses
`scipy_arpack_splu_reciprocal_linear_buckling.v1`. It factors the positive
definite elastic stiffness with sparse SuperLU and applies ARPACK to the
matrix-free reciprocal operator

```text
K^-1 Kg phi = mu phi,  lambda = 1 / mu.
```

This formulation permits singular positive-semidefinite geometric stiffness.
The operator's returned modes must be materially real and pass the original
`K phi = lambda Kg phi` relative-residual gate.

Both paths:

- require finite square matrices and reject material asymmetry or
  indefiniteness;
- use a deterministic starting vector and canonicalize complete clustered
  eigenspaces in the physical metric;
- reject a request that cuts a repeated eigenvalue cluster;
- keep the requested subspace below SciPy's dense-fallback threshold;
- report canonical CSR input hashes plus raw and semantic result hashes; and
- report `regularization_applied=false` and `fallback_used=false`.

## Whole-model connection and exact boundary

The explicit API/CLI backend values are:

```text
modal:            scipy_arpack_symmetric_generalized_modal.v1
linear_buckling:  scipy_arpack_splu_reciprocal_linear_buckling.v1
```

The current frame/truss assemblers still create global dense NumPy matrices.
Only the reduced matrices passed to the eigensolver are converted to CSR.
Results therefore state all of the following:

```text
whole_model_assembly_storage = dense_numpy_binary64
native_sparse_assembly_used = false
sparse_eigen_extraction_used = true
```

Sparse buckling reports lower bounds for the finite positive eigenvalue count
and geometric-stiffness positive rank. It does not present an exact full
spectrum count from a partial extraction.

The implementation is bounded to 4,096 free DOFs to prevent accidental use as
an unbounded production path. Large binary mode-vector artifacts, native
sparse modal/buckling assembly, conditioning policy for production scale,
independent Level 2 comparison, and release promotion remain open.

## Verification

Run the focused contract and whole-model parity tests:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_sparse_generalized_eigen.py \
  tests/test_whole_model_modal_analysis.py \
  tests/test_whole_model_buckling_analysis.py
```

The tests cover dense-reference parity, singular `Kg`, deterministic replay,
cluster canonicalization and cut rejection, invalid matrices, the no-dense-
fallback subspace bound, and explicit whole-model result boundaries.

