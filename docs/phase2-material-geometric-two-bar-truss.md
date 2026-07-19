# Phase 2 stateful material-geometric two-bar truss

## Outcome

This increment adds one bounded Level-1 analytic benchmark that couples the
existing state-updated combined-hardening steel integration point to exact
current-chord truss kinematics. It closes neither a general truss formulation
nor the product G1 gate.

The deterministic reference run reports:

- 2 free apex equations and 2 independent material states;
- 17/17 committed cyclic force targets;
- 3 accepted steps that change material state and one plastic-flow reversal;
- `0.14250045676880574 MJ/m3` final nonnegative dissipated energy density;
- `8.493472591908358e-11 kN` maximum accepted residual infinity norm;
- `6.255412854372366e-15 m` maximum displacement difference from the
  independent symmetric scalar reduction;
- `5.327070199754454e-10` coupled tangent relative finite-difference error;
- three quadratic-convergence observations with maximum ratio
  `0.055005450639694906`;
- 58 recorded line-search evaluations, zero regularization, and zero fallback;
- an intentionally failed plastic trial that restores the exact accepted
  structural and material bytes.

The benchmark returns `status=partial` with `contract_pass=true`. `partial` is
intentional because the receipt is narrower than a production element path.

## Formulation

For each bar, the current chord is

```text
r = xj + uj - xi
l = ||r||
n = r / l
epsilon = (l - L0) / L0
```

The existing one-dimensional backward-Euler return mapping evaluates stress
`sigma`, trial material state, and algorithmic tangent `Et` from one immutable
committed state. The axial force and apex internal force are

```text
N = A sigma
f_internal = N n
```

The exact displacement derivative is split explicitly:

```text
K_material  = A Et / L0 * (n outer n)
K_geometric = N / l * (I - n outer n)
K_consistent = K_material + K_geometric
```

Stress in MPa and area in square metres are converted to kN by the fixed factor
`1000`. The residual is `F_internal - load_factor * F_reference`, bound to the
existing residual-formula hash.

## Verification contracts

### Same-parent tangent

Every central-difference perturbation is evaluated from the same committed
constitutive parent. At a plastic compressed configuration:

- the full tangent matches the residual derivative within `5.33e-10` relative;
- the material-only tangent error is about `3.36e-2`;
- the geometric-only tangent error is about `1.00`;
- both omitted-term errors exceed the full error by more than two orders of
  magnitude;
- the tangent is symmetric to the stated tolerance; and
- the committed parent bytes and hash do not change.

### Newton and scalar reduction

The full solver retains both apex coordinates. A separate scalar equation uses
symmetry to solve only the vertical coordinate with a bracketed Brent root.
The structural algebra is independent, while both paths intentionally share
the already verified uniaxial return mapping and the same committed material
parent. The benchmark records this shared dependency instead of representing
the comparison as independent code-to-code evidence.

An elastic probe shows the expected local quadratic Newton sequence. The
cyclic path records every convergence and line-search history and commits a
material state only after both residual and increment gates pass.

### Commit and rollback

One deliberately iteration-limited load attempt reaches a yielded trial state
and is rejected. The returned accepted state is the original object, its
canonical state bytes are unchanged, and both integration-point byte strings
match the parent. This is a rollback contract test, not a successful physical
load step.

### Objectivity

A single bar subjected to a rigid 90-degree rotation preserves its length,
zero strain, zero axial force, and zero geometric tangent. This checks the
current-chord kinematics independently of the two-bar equilibrium path.

## Files

- `src/structural_analysis/benchmark/material_geometric_truss.py`
- `tests/test_material_geometric_truss_benchmark.py`

## Claim boundary

The receipt may support only these bounded claims:

- one planar two-bar material-geometric coupling case;
- exact current-chord axial kinematics;
- an algorithmic material tangent plus an initial-stress geometric tangent;
- same-parent finite-difference consistency;
- stateful Newton commit/rollback;
- cyclic plastic dissipation; and
- agreement with the explicitly disclosed symmetric scalar reduction.

It does **not** establish:

- a general 2D/3D corotational truss, frame, or shell implementation;
- distributed plasticity or a finite-strain material law;
- arc-length traversal of the material-geometric limit point;
- external code-to-code, published, experimental, or customer-shadow evidence;
- production sparse or ROCm/HIP execution;
- full-building equilibrium; or
- G1 closure.

Those limitations are emitted as machine-readable false claims and blockers in
the benchmark receipt.
