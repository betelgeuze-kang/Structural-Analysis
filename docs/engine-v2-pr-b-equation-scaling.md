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
ExecutionPlan schema version remains v1 through the compatibility rule below.

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
identifies the scaling artifact. Validation reconstructs the base-plan hash by
removing the typed extension and fails closed on stale bindings.

Replay equality is defined after model/unit adapters normalize coordinates to
meters, translational loads to newtons, and moments to newton-meters.
`validate_equation_scaling` can replay the commitment against the exact source
arrays and fails if the committed bytes, characteristic length, or free-scope
reference force differ.

## Required extension boundary

`ExecutionPlan.required_extensions` reads a sorted immutable list from the typed
`engine-v2:required-extensions` extension. Binding equation scaling adds that
declaration extension and lists `engine-v2:equation-scaling` as required.
Validation fails when a required extension is missing, unsupported, or present
without its required declaration. Reconstructing the unbound plan removes both
typed extensions before checking `base_plan_hash`.

An unscaled PR-A plan from merged PR #103 has neither extension; its manifest
shape and plan hash remain unchanged. The declaration stays inside the existing
forward-compatible `extensions` namespace, so no top-level v1 field is added.
This is the backward-compatible path for the extracted backend-neutral plan
contract. A solver that requires scaled convergence must consume the bound
plan, where `ExecutionPlan.required_extensions` is non-empty.

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
refinement tests, a reviewed public extension API, and descriptor-based vector
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

Focused tests cover force/moment policy values, source commitment replay,
constrained-load exclusion from free-scope scaling, required extension
enforcement, plan/state hash binding, SI replay, immutable arrays, dimensional
norm separation, deterministic governing DOF selection, strict JSON types and
unknown fields, malformed active equation sets, invalid geometry/load inputs,
and stale hashes.

`Engine v2 Contract CI` runs this complete backend-neutral suite on a
GitHub-hosted Python 3.10 runner. It is a schema/static/CPU contract lane only;
it does not produce HIP, external, numerical-closure, or readiness evidence.
The PR body historically records `63 passed`, while a fresh collection of the
current PR head yields 64 tests. The workflow runs the complete file pattern
rather than hard-coding or hiding that one-test drift.

```bash
python3 -m pytest -q tests/test_engine_v2*.py
python3 -m ruff check src/structural_analysis/engine_v2 \
  tests/test_engine_v2_equation_scaling_v1.py \
  tests/test_engine_v2_core_dependency_boundary.py
python3 -m ruff format --check src/structural_analysis/engine_v2 \
  tests/test_engine_v2_equation_scaling_v1.py \
  tests/test_engine_v2_core_dependency_boundary.py
```
