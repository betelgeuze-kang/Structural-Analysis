# Experimental sparse modal and buckling extraction

The independent Python modal and linear-buckling kernels expose bounded sparse
low-mode extraction. The current authoritative whole-model modal driver remains
dense and does not connect these sparse kernels. The sparse paths are
experimental and do not expand release authority.

## Backend contracts

`solve_sparse_modal_modes` accepts CSR stiffness and mass matrices. Exact
diagonal pairs use `analytic_exact_diagonal_generalized_modal.v1`, which knows
every diagonal generalized eigenvalue and rigid multiplicity directly.

Coupled pairs use `source_bound_count_guarded_sparse_modal.v1`. They retain the
existing symmetry projection and numerical mass-conditioning/stiffness-PSD
policies. ARPACK still supplies the explicitly reported conditioning and
largest-eigenvalue estimates; partial ARPACK low-mode extraction is not used to
claim full rigid multiplicity or complete repeated clusters.

Counts over `K/I` and `M/I` also check every direction at the actual binary64
cutoffs of the existing numerical input policy. The stiffness guard permits
equality at its negative PSD cutoff; the mass guard requires strict positivity
above its conditioning cutoff. These point checks do not enclose the error of
the estimates used to calculate those cutoffs. The temporary `K/I` pencil is
closed before `M/I` and `K/M` remain live, keeping the same two-context bound.

A live source-bound interval count session certifies the global positive
prefix, selected full clusters and outside guards. It also counts at the actual
binary64-rounded threshold used by the public caller. If that inclusive count
differs from the certified prefix, the call refuses instead of silently changing
the threshold policy. Cold coordinate augmentation and sparse shifted solves
extract the complete selected numeric space. Canonicalization, relative
residuals, M-orthogonality and stiffness diagonalization are checked in the
original projected matrices. Rigid modes are excluded without regularization.

Only successful counts for the same immutable source pair and exact shift are
reused within the live session. Constructor/SPD/query/error/close and lookup
costs share one cumulative bounded ledger. External or serialized certificates
do not grant proof authority or reset cost. Independent calls have separate
session custody, and overlapping use of the same pipeline is rejected.

`candidate_eigenpair_count` is the number of materialized selected pairs in the
coupled path; count intervals and known rigid multiplicities are not counted as
materialized eigenpairs. Exact diagonal pairs continue to report their complete
analytical candidate spectrum. The legacy `SPARSE_MODAL_PROFILE` string remains
available to callers but is not the effective coupled-result profile.

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
- use deterministic bounded extraction and canonicalize complete clustered
  eigenspaces in the physical metric;
- reject a request that cuts a repeated eigenvalue cluster;
- keep the requested subspace below SciPy's dense-fallback threshold;
- report canonical CSR input hashes plus raw and semantic result hashes; and
- report `regularization_applied=false` and `fallback_used=false`.

## Whole-model and numerical boundary

The independent kernel result profiles are:

```text
modal diagonal:   analytic_exact_diagonal_generalized_modal.v1
modal coupled:    source_bound_count_guarded_sparse_modal.v1
linear_buckling:  scipy_arpack_splu_reciprocal_linear_buckling.v1
```

The current frame/truss assemblers still create global dense NumPy matrices.
`run_authoritative_modal` uses its existing small-dense backend and reports:

```text
sparse_backend_used = false
sparse_modal_backend_connected = false
```

Sparse buckling reports lower bounds for the finite positive eigenvalue count
and geometric-stiffness positive rank. It does not present an exact full
spectrum count from a partial extraction.

Kernel input is bounded to 4,096 DOFs, with tighter per-query, cumulative
arithmetic/storage, rank and iteration limits. A valid matrix can therefore be
refused under a resource or interval-uncertainty bound. No budget increase,
hidden retry, exact fallback or dense model fallback occurs. Positive
`maximum_iterations` tightens both thin-block and total iteration limits;
`None` keeps the bounded defaults. `arpack_tolerance` continues to govern the
retained numerical admission estimates. Zero residual or orthogonality
tolerance means the literal zero target, not an implicit epsilon.

The count guards do not enclose the error of the ARPACK largest estimate or
provide directed-rounded vector error bounds. Numerical conditioning estimates,
whole-model/CLI sparse integration, binary mode-vector artifacts, native sparse
assembly, independent Level 2 comparison, whole-cost gains and release promotion
remain separate and open.

## Verification

Run the focused contract and whole-model parity tests:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_sparse_generalized_eigen.py \
  tests/test_sparse_diagonal_modal_nullity.py \
  tests/test_sparse_coupled_modal_completeness.py \
  tests/test_sparse_live_modal_pipeline.py \
  tests/test_whole_model_modal_analysis.py \
  tests/test_whole_model_buckling_analysis.py
```

The tests cover complete repeated free-chain spaces and four-component rigid
multiplicity, permutation and deterministic replay, source/rounded-threshold
custody, cumulative cost and concurrent sessions, cluster-cut rejection, invalid
matrices, singular `Kg`, no dense fallback, and the existing dense whole-model
boundary. Kernel tests and hosted checks do not establish physical validation
or release readiness.
