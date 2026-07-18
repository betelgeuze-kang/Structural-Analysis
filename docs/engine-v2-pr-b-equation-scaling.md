# Engine v2 PR B — Equation scaling

## Scope

PR B adds deterministic equation scaling after the backend-neutral core
contracts and before any Krylov recurrence. It does not add a solver,
preconditioner, result authority, CPU/HIP execution, hardware claim, or
convergence decision.

The contract consumes coordinates and one reference equation-load vector that
have already been normalized to SI. It produces an immutable per-equation
divisor vector and binds its content hash into `ExecutionPlan v1` through the
typed `engine-v2:equation-scaling` extension. The extension is covered by the
aggregate plan hash and appears in `required_extensions`; a consumer cannot
validate a bound plan after silently dropping the scaling extension. The public
ExecutionPlan schema version remains v1, while a distinct scaled capability
profile makes cross-version negotiation fail closed.

## Policies

### Characteristic length

Policy: `two_max_radius_from_fsum_centroid.v1`

For SI node coordinates `x_i`, the centroid is accumulated component-wise with
`math.fsum`, and

```text
x_bar = (1 / node_count) sum_i x_i
L_char = 2 max_i ||x_i - x_bar||_2
```

The pass is O(N), invariant to translation and rigid rotation, and returns the
span for a two-node member. A finite positive minimum is an explicit hashed
input (default `1e-12 m`). Degenerate geometry fails closed; it is not silently
clamped.

### Reference force and equation divisors

Policy: `max_translation_or_equivalent_moment_with_floor.v1`

The reference scope is explicitly `free_equations`. The source input remains a
full global-equation vector in canonical order so its exact bytes can be
committed, but constrained-equation entries do not set the scale used by the
solver recurrence. They belong to reaction observation, not the reduced solve.

For the free-equation subset of that reference load vector,

```text
F_ref = max(F_min,
            max(abs(free translational reference loads)),
            max(abs(free rotational reference loads)) / L_char)

s_j = F_ref            for UX, UY, UZ equations
s_j = F_ref * L_char   for RX, RY, RZ equations
r_scaled_j = r_raw_j / s_j
```

`F_min` is an explicit hashed input (default `1 N`). Translational divisors are
in N, rotational divisors are in N·m, and scaled residuals are dimensionless.
The vector is canonical little-endian fp64 with immutable byte backing.

### Fully constrained plans

An unscaled `ExecutionPlan` may represent a fully constrained model with an
empty `free_dofs` partition. That model has no reduced recurrence space, so it
is not a zero-length Krylov solve. Creating or binding `EquationScaling` for
such a plan fails closed with `free_equation_space_empty`.

`ScaledResidualTrace` therefore retains its nonempty `active_equations` and
non-null governing node/DOF contract. A future compiler/executor must route a
fully constrained model to a separate `no_solve/reaction_only` disposition;
reaction observation remains dimensional and is not convergence or ResultIR
authority in this PR.

## Hash and replay boundaries

`EquationScaling` records:

- the exact unbound `ExecutionPlan` hash;
- the source `model_ir_content_hash` and `load_pattern_id`;
- the selected `free_equations` reference scope and exact `free_dofs` content
  hash;
- canonical raw-byte and metadata-plus-byte hashes for the SI node coordinates
  and the full SI reference equation-load vector;
- an aggregate source-commitment hash covering those identities and descriptors;
- the equation-order hash over node IDs, DOF components, node/DOF mapping, and
  DOF count;
- policy names and explicit minima;
- characteristic length and reference force;
- raw-byte and metadata-plus-byte vector hashes;
- an aggregate scaling hash.

Binding creates a new plan hash without a circular dependency: the scaling
artifact identifies the unbound base plan, while the bound plan extension
identifies the scaling artifact and repeats its ModelIR, load-pattern, and
free-partition identities. Validation reconstructs the exact unbound base plan,
restores its original capability profile, and passes that plan into
`validate_equation_scaling`. A self-consistent scaling artifact for another
source therefore fails before the extension values are compared.

Replay equality is defined after model/unit adapters normalize coordinates to
meters, translational loads to newtons, and moments to newton-meters.
`validate_equation_scaling` can replay the commitment against the exact source
arrays and fails if the committed bytes, characteristic length, or free-scope
reference force differ. `bind_equation_scaling_to_execution_plan` requires both
source arrays and performs that full replay; callers cannot create a bound plan
from manifest self-consistency alone. Later artifact readers may call
`validate_equation_scaling_binding` without arrays for identity checks, but a
solver compiler path must supply both arrays for derivation authority.

## Required extension boundary

`ExecutionPlan.required_extensions` reads a sorted immutable list from the typed
`engine-v2:required-extensions` extension. Binding equation scaling adds that
declaration extension and lists `engine-v2:equation-scaling` as required.
Validation fails when a required extension is missing, unsupported, or present
without its required declaration. Reconstructing the unbound plan removes both
typed extensions before checking `base_plan_hash`.

An unscaled PR-A plan from merged PR #103 has neither extension; its manifest
shape, `engine_v2_core_linear_static` capability profile, and plan hash remain
unchanged. The fixed PR-A regression value is
`sha256:fcebd59b39c25e38c4cfc72f542a57737e21fb7af2b4b9055eb75e83fc62af33`.
A bound plan uses `engine_v2_core_scaled_linear_static`. PR-A readers only know
the original profile and therefore reject scaled plans instead of accepting the
new extensions as opaque data. PR-B readers require the scaled profile and both
typed extensions together. This preserves unscaled v1 bytes while providing
backward fail-closed negotiation for the new contract.

Object-level and manifest-only validation both reconstruct the unbound plan
hash and recompute the equation-order identity. They also compare the binding's
ModelIR hash, load-pattern ID, and free-DOF descriptor hash directly with the
plan. Manifest validation does not recover array bytes or prove source
derivation; that deeper authority requires the object arrays and the mandatory
bind-time source replay above.

### Pre-merge migration note

The earlier draft two-argument call
`bind_equation_scaling_to_execution_plan(plan, scaling)` is intentionally no
longer valid. Callers must pass keyword-only `node_coordinates_m` and
`reference_equation_load_si`; explicit `None` values fail closed. Serialized
bound plans also move from `engine_v2_core_linear_static` to
`engine_v2_core_scaled_linear_static`. Unscaled PR-A plans require no migration,
as demonstrated by fixed plan-hash and canonical-manifest-byte regressions.

## Residual observation boundary

`ScaledResidualTrace` is explicitly `non_authoritative_diagnostic`. It records
raw and scaled vectors, active equations, vector hashes, and a deterministic
governing node/DOF. Its equation scope is fixed to `free_equations`, and the
active set must exactly equal `ExecutionPlan.free_dofs`. Ties in absolute scaled
residual use the smallest free equation index.

There is deliberately no single norm over mixed N and N·m quantities. The trace
reports separate raw translational norms in N, raw rotational norms in N·m, and
dimensionless scaled norms. It carries no `converged`, terminal, backend,
hardware, or authoritative result field.

## Dependency and mainline boundary

The implementation imports only the Engine v2 canonical/core contracts,
NumPy, jsonschema, and the Python standard library. It does not materialize or
import ResultIR/DiagnosticIR, FGMRES, fixed-rank coarse correction, HIP/ROCm,
runtime, viewer, molecular, or product-readiness modules.

PR C may consume the immutable scale vector and trace policy when implementing
the CPU FGMRES recurrence, but it must own convergence and terminal semantics.
It must consume the bound `ExecutionPlan`, required scaling extension, exact
free-DOF scale selection, and reduced-CSR identity. Its observation must retain
raw translational norm [N], raw rotational norm [N·m], dimensionless scaled
norm, governing node/DOF, scaling hash, and plan hash. ResultIR authority is not
part of that extraction; recurrence, checkpoint, and terminal observation come
first.

Before PR C, the PR-A follow-up lane must resolve the
`time_function`/`construction_stage` round-trip ID defect, self-weight-only load
patterns, content-derived unsupported-feature blockers, semantic versus
provenance ModelIR hashes, global versus reduced CSR identity, and the StateIR
large-vector storage profile. These are follow-up contracts, not claims closed
by PR B.

Later PR-B follow-ups are Linux/Windows golden hashes, characteristic-length
refinement tests, a reviewed general extension API, and descriptor-based vector
artifact storage. They are intentionally not mixed into this pre-merge fix.

## Review and rollback

This PR exceeds the preferred 2,000-line review target because the strict JSON
schemas, semantic validators, negative tests, and dedicated CI must move
together before the first solver consumer. It still owns one public contract,
contains no generated evidence, and remains below the 25-file limit. Review in
this order: schemas, `execution_plan.py`, `equation_scaling.py`, focused tests,
then workflow/docs.

Rollback is a revert of PR B. The unscaled PR-A `ExecutionPlan` manifest and
hash are byte-for-byte preserved, so rollback does not require a PR-A artifact
migration or evidence regeneration.

## Verification

Focused tests cover force/moment policy values, mandatory bind-time source
commitment replay,
constrained-load exclusion from free-scope scaling, required extension
enforcement, scaled-profile negotiation, reconstructed-base cross-artifact
validation, manifest-only typed semantics, the fixed PR-A manifest/hash,
plan/state hash binding, SI replay, immutable arrays, dimensional norm
separation, deterministic governing DOF selection, strict JSON types and
unknown fields, malformed active equation sets, invalid geometry/load inputs,
and stale hashes.

`Engine v2 Contract CI` runs the complete Engine v2 file pattern and
`tests/test_model_ir_v2_contract.py` on a GitHub-hosted Python 3.10 runner. The
ModelIR source and schema paths therefore have a matching test owner in this
lane. It is a schema/static/CPU contract lane only; it does not produce HIP,
external, numerical-closure, or readiness evidence.

```bash
python3 -m pytest -q tests/test_engine_v2*.py tests/test_model_ir_v2_contract.py
python3 -m ruff check src/structural_analysis/engine_v2 \
  src/structural_analysis/model_ir \
  tests/test_engine_v2_equation_scaling_v1.py \
  tests/test_engine_v2_core_dependency_boundary.py \
  tests/test_model_ir_v2_contract.py
python3 -m ruff format --check src/structural_analysis/engine_v2 \
  src/structural_analysis/model_ir \
  tests/test_engine_v2_equation_scaling_v1.py \
  tests/test_engine_v2_core_dependency_boundary.py \
  tests/test_model_ir_v2_contract.py
```
