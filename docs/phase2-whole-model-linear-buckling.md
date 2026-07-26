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

All source-bound receipt cases use the default dense binary64 backend, expose
separate raw and semantic result hashes, and report no regularization or
fallback. A separate opt-in experimental sparse reciprocal extraction path is
documented in `docs/sparse-modal-buckling.md`; it does not alter this receipt's
authority. The public result
inlines only max-component-normalized small-dense shapes; stiffness-normalized
vectors are represented by SHA-256 and are not mislabeled as connected binary
vector artifacts.

Current bindings:

- result artifact:
  `sha256:747b68fc1623d73d9cd100d41e6c35db05a267988821f8941674551cb7f603fb`
- source-set:
  `sha256:8353f7b6a3dd11cf42a96dd3c17554fcbc7ba9132dc9ea8155f8e6d858301203`

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
material-geometric coupling, native sparse assembly or production extraction, large-mode binary
artifacts beyond the separate small code-to-code vectors, ROCm/HIP parity, a
broad independent buckling corpus beyond the separate one-column CalculiX B32
technical comparison, Verification Level 2, commercial equivalence, or release
readiness.
