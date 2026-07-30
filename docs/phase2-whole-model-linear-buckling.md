# Phase 2 bounded whole-model linear buckling

This slice connects the strict generalized-eigen buckling kernel to the public
`load_model` / `analyze` API for an explicitly bounded 3D frame path. The
analysis type is `linear_buckling`.

## Reference-state and initial-stress contract

1. The authoritative dense linear-static solver runs the selected nodal load
   case at reference load factor `1.0`.
2. Local frame end forces are recovered, and constant element compression is
   computed as `(FX_I - FX_J) / 2` after an axial-equilibrium check.
3. Each positive compression force scales the consistent Euler-Bernoulli
   initial-stress matrix. The local matrices are transformed through the same
   local-axis and rigid-offset mapping as elastic stiffness.
4. The reduced public path solves `K phi = lambda Kg phi`, equivalently locating
   loss of positive definiteness of `K - lambda Kg`.
5. The common source-bound 6DOF characteristic length defines a symmetric
   coordinate transform `C`. Eigen extraction uses `C^T K C` and `C^T Kg C`;
   every vector is recovered with `phi = C q` and rechecked against the original
   physical matrices before publication. The result binds the scaling manifest
   and reports exact scaled condition numbers through 256 reduced equations.

The sign convention is deliberately strict. Compression contributes a
positive-semidefinite `Kg`; tension is not discarded, absolute-valued, or
projected. A tension member or a reference state with no positive compression
fails closed. This keeps the matrix contract scientifically explicit while a
future indefinite mixed-stress formulation remains unimplemented.

Only explicit `frame`, `beam`, and `column` elements with nodal reference loads
are accepted. Truss/shell geometric stiffness and distributed, thermal,
settlement, or follower-load conversion are not inferred.

## Source-bound verification gates

The committed receipt executes four public-path gates:

| Gate | Truth basis | Recorded result |
| --- | --- | --- |
| Two-plane pinned column | 16-element convergence to `pi^2 EI/L^2` | load factors `131.59499646070574`, `175.45999528098105`; maximum relative error `2.060210824908061e-06` |
| Reference-load scaling | Linear homogeneity | `100 kN` and `200 kN` reference patterns both give physical critical load `13159.499646070575 kN` |
| Symmetric bending cluster | Complete repeated eigenspace | one-mode request blocked; complete two-mode request ready |
| Reference axial sign | Positive-compression invariant | tension and zero-compression reference states both blocked without fallback |

All ready cases use dense binary64 matrices, expose separate raw and semantic
result hashes, and report no regularization or fallback. The public result
inlines only max-component-normalized small-dense shapes; stiffness-normalized
vectors are represented by SHA-256 and are not mislabeled as connected binary
vector artifacts.

Current bindings:

- result artifact:
  `sha256:78be972e72e00ee4c01f42abd4c1be23b9ed8380d36cecc376e7eb5f7d84a6c8`
- source-set:
  `sha256:09cff3a3b7db551c2ad08cf9c0b172a13a5b9ca67015f028c8ca35d5212a4168`

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_whole_model_buckling_result.json`
- `implementation/phase1/release_evidence/productization/phase2_whole_model_buckling_summary.json`
- `src/structural_analysis/schemas/whole_model_buckling_v1.schema.json`

Run:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_whole_model_buckling_analysis.py \
  tests/test_build_phase2_whole_model_buckling_artifacts.py
PYTHONPATH=src python3 scripts/build_phase2_whole_model_buckling_artifacts.py
PYTHONPATH=src python3 scripts/build_phase2_whole_model_buckling_artifacts.py --check
```

## Explicit non-claims

The receipt remains `status=partial`. It does not establish general frame/shell
stability, mixed tension-compression initial stress, truss/shell geometric
stiffness, nonlinear buckling, post-buckling path following, imperfections,
material-geometric coupling, sparse production extraction, large-mode binary
artifacts beyond the separate small code-to-code vectors, ROCm/HIP parity, a
broad independent buckling corpus beyond the separate one-column CalculiX B32
technical comparison, Verification Level 2, commercial equivalence, or release
readiness.

The source-bound package at
`artifacts/vv/bounded_planar_external_modal_buckling_case_package/` adds an exact
three-member portal input with 16 product linear elements per member mapped to
eight circular-section CalculiX B32 elements per member. The repository-local
same-operator supplemental bundle now attaches an actual CalculiX 2.17 result;
both factors pass the declared 5 percent tolerance at approximately 1.78 and
0.165 percent relative error. Consequently `buckling.portal` is fresh technical
evidence in the V&V matrix, while independent operation, legal approval,
Verification Level 2, commercial equivalence, and release readiness remain false.
