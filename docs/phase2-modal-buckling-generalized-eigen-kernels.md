# Phase 2 modal and buckling generalized-eigen kernels

This slice adds strict deterministic dense-matrix kernels for

- modal analysis: `K phi = omega^2 M phi`; and
- linear buckling: `K phi = lambda Kg phi`.

The modal path requires symmetric positive-semidefinite `K` and symmetric
positive-definite `M`. The buckling path requires symmetric positive-definite
`K` and symmetric positive-semidefinite `Kg`; singular `Kg` is allowed, and
infinite generalized eigenvalues are excluded from the finite positive mode
set. Inputs are finite binary64 square matrices. The solvers do not add diagonal
regularization and do not use a fallback solver.

Repeated eigenvalues are handled as complete clusters. A coordinate-axis
projector constructs a deterministic metric-orthonormal basis for each cluster.
If `mode_count` would cut through a repeated or tolerance-clustered group, the
request fails closed instead of exposing a library-dependent partial basis.
Every result contains both a raw binary64 SHA-256 and a tolerance-normalized
`canonical-json-scientific-12e` semantic SHA-256.

The source-bound receipt covers four narrow gates:

1. the two eigenvalues of a closed-form two-DOF shear modal system;
2. a diagonal linear-buckling system with rank-deficient `Kg` and two finite
   positive factors;
3. a 16-element pinned Euler column compared with `pi^2 EI/L^2`; and
4. modal and buckling repeated-eigenspace basis determinism plus fail-closed
   incomplete-cluster selection.

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_modal_buckling_kernel_result.json`
- `implementation/phase1/release_evidence/productization/phase2_modal_buckling_kernel_summary.json`
- `src/structural_analysis/schemas/modal_buckling_kernel_v1.schema.json`

Run:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_modal_generalized_eigen_v1.py \
  tests/test_buckling_generalized_eigen_v1.py \
  tests/test_build_phase2_modal_buckling_kernel_artifacts.py
PYTHONPATH=src python3 scripts/build_phase2_modal_buckling_kernel_artifacts.py
PYTHONPATH=src python3 scripts/build_phase2_modal_buckling_kernel_artifacts.py --check
```

The receipt is intentionally `status=partial` even when all four gates pass.
This matrix-kernel receipt does not by itself connect whole-model mass or
geometric-stiffness assembly. Separate source-bound receipts now connect a
bounded dense frame/truss consistent-mass modal path and a compression-only frame
reference-state linear-buckling path through the public API; see
`docs/phase2-whole-model-modal-analysis.md` and
`docs/phase2-whole-model-linear-buckling.md`. These receipts do not establish a
general frame/shell modal or stability workflow, mixed tension-compression,
nonlinear buckling, an independent Level 2 comparison, published/experimental
validation, sparse production execution, ROCm/HIP parity, commercial
equivalence, or release readiness.
