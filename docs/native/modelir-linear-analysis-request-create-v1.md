# ModelIR linear analysis-request creation v1

`structural-workbench model-create-linear-analysis-request` is a bounded native selection surface
for the existing `model_ir_linear_cpu_v1` product. It creates a strict, model-bound CPU/PCG request
from one C++-validated ModelIR v2 document and never modifies or executes the source model.

```text
structural-workbench model-create-linear-analysis-request MODEL.json \
  --case CASE-ID --load-pattern PATTERN-ID \
  --max-iterations 100 \
  --absolute-residual-tolerance 1e-11 \
  --relative-residual-tolerance 1e-13 \
  --maximum-increment 0 \
  --output-dir REQUEST-DIR
```

The option order and vocabulary are fixed. The case and load-pattern identities are bounded by the
strict analysis-request contract. Iterations are in `1..=1000000`; tolerances and maximum increment
are finite and nonnegative, and at least one residual tolerance is positive. Backend and operation
are closed to `cpu` and `solve_model_ir_linear_static`.

## Validation, preflight, and publication

Rust strictly parses the source and crosses Rust -> C ABI -> C++ semantic validation. Invalid or
explicitly blocked models fail closed. The named load pattern must exist and declare
`linear_static`. Rust builds and reparses the typed
`structural-model-ir-linear-analysis-request.v1` document with the exact source content, semantic,
and provenance hashes.

Before publication, the request enters the same product preparation path as execution. ABI v1.13
C++ constructs the constraint-reduced frame3d/truss3d operator and recovery layout, and Rust
constructs and validates the derived canonical PCG request. Unsupported elements, offsets,
releases, prescribed constraints, selectors, bounds, or sparse-request drift therefore fail before
an executable-request receipt is emitted. No PCG iteration is started by this command.

The create-new output directory contains only canonical `analysis-request.json` and self-hashed
`request-receipt.json`. The receipt binds the source bytes, all three ModelIR identities, selected
case/load/backend/config, exact request hash, C++ assembly hash, generated sparse-request hash,
artifact bytes, and both semantic-snapshot and assembly-preflight facts. Existing destinations and
all invalid inputs fail without partial publication.

CPU static/shared installed-package E2E v22 runs creation twice under an empty `PATH`, proves exact
artifact identity and source nonmutation, then uses the generated request—not the fixture path—for
the installed Import -> Validate -> Run -> Resume -> Compare -> Report workflow. Frozen v1 through
v21 distribution receipts retain their narrower authority.

## Claim boundary

This closes native request construction for one existing bounded CPU linear-static solver profile.
It does not add arbitrary backends, preconditioners, direct/indefinite solvers, nonlinear, modal,
buckling, transient, HIP, or free-form solver selection; it does not edit the model, prove
convergence for every valid operator, or make an engineering acceptance decision. Broad solver
selection, React/TypeScript removal, approved HIP C2, and C6 remain open.
