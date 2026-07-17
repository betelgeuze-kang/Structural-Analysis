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
aggregate plan hash; the public ExecutionPlan schema version remains v1.

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

For the reference load vector in canonical equation order,

```text
F_ref = max(F_min,
            max(abs(reference translational loads)),
            max(abs(reference rotational loads)) / L_char)

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

## Residual observation boundary

`ScaledResidualTrace` is explicitly `non_authoritative_diagnostic`. It records
raw and scaled vectors, active equations, vector hashes, and a deterministic
governing node/DOF. Ties in absolute scaled residual use the smallest active
equation index.

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

## Verification

Focused tests cover force/moment policy values, plan/state hash binding, SI
replay, immutable arrays, dimensional norm separation, deterministic governing
DOF selection, strict JSON types and unknown fields, malformed active equation
sets, invalid geometry/load inputs, and stale hashes.

```bash
python3 -m pytest -q tests/test_engine_v2*.py
python3 -m ruff check src/structural_analysis/engine_v2 \
  tests/test_engine_v2_equation_scaling_v1.py \
  tests/test_engine_v2_core_dependency_boundary.py
python3 -m ruff format --check src/structural_analysis/engine_v2 \
  tests/test_engine_v2_equation_scaling_v1.py \
  tests/test_engine_v2_core_dependency_boundary.py
```
