# Stateful corotational steel-frame cyclic benchmark

This benchmark connects the existing small-strain bilinear steel return
mapping to the accepted-state corotational fiber-frame Newton path. It is a
bounded internal material-breadth case, not an external cyclic-member
validation.

## Case

The model is a two-member planar cantilever:

- nodes at `(0, 0)`, `(1, 0)`, and `(2, 0)` m;
- the first node is fixed in all three planar DOFs;
- a `-50 kN` reference vertical load acts at the tip;
- each member uses three Gauss points and the stateful axial-curvature fiber
  section;
- the load-factor history rises to `+1`, reverses to `-1`, and returns to
  `+1` in 30 accepted targets.

The section protocol currently requires both steel and concrete fibers. This
case therefore uses ordinary steel fibers and explicit carrier concrete with
`E = 1 MPa` and tension/compression strengths of `1e12 MPa`. The carrier stays
elastic and contributes negligible stiffness. Every accepted step requires
zero damaged members and zero concrete damage dissipation. The case is
described as **steel-dominated**, not as a pure-steel section.

Three steel variants share `E = 200000 MPa`, `fy = 250 MPa`, and total linear
hardening modulus `8000 MPa`:

1. pure isotropic hardening;
2. pure kinematic hardening;
3. combined `3000 MPa` isotropic plus `5000 MPa` kinematic hardening.

## Independent elastic prefix

Before yield, the specified fibers give

```text
EI = 10241 kN m^2
```

The first `5 kN` step is checked against the Euler-Bernoulli cantilever value

```text
v_tip = P L^3 / (3 EI)
```

with a relative tolerance of `1e-6`. All three variants must have the same
elastic tip displacement to `1e-13 m` because their elastic modulus and
section geometry are identical.

## Stateful nonlinear contract

Every Newton trial starts from one immutable accepted frame checkpoint. The
free-equation residual and tangent are

```text
r(q, lambda) = F_internal(q; state_n) - lambda F_reference
K_consistent = K_material + K_geometric
```

At the first yielded target, every Jacobian column is checked by a central
difference. The center, forward, and backward evaluations all use the same
accepted material and kinematic parent. The check also requires:

- material and geometric tangent terms both active;
- symmetric free-equation tangent;
- exact tangent decomposition;
- yielded steel fibers and zero damaged concrete fibers;
- local full-step convergence order of at least `1.8` for the observed
  first-yield Newton window.

Each accepted step records the residual norm, iteration count, line-search
history, yield/damage counts, checkpoint hash, tip displacement, and total
section dissipation. Every full path is replayed from the initial checkpoint
and must reproduce the same path dictionary and final canonical checkpoint
bytes.

A forced `max_iterations=0` attempt starts from the accepted `lambda=0.8`
combined-hardening state and targets `lambda=1.0`. Its trial response reaches
steel yield, but the solver returns the exact parent checkpoint bytes and does
not claim convergence.

## Hardening-branch observation

The cyclic path intentionally distinguishes constitutive branches:

- kinematic and combined hardening first re-yield on the reverse branch at
  step 19;
- pure isotropic hardening first re-yields at step 20;
- final dissipated energy is ordered
  `kinematic > combined > isotropic > 0`;
- dissipation is nonnegative and monotonic for every variant.

These are internal algorithmic observations for this load history. They are
not calibrated experimental hysteresis acceptance.

## Run

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python -m pytest -q \
  tests/test_stateful_corotational_steel_frame_cyclic_benchmark.py
```

The reusable entry point is
`build_stateful_corotational_steel_frame_cyclic_benchmark` in
`structural_analysis.benchmark`.

## Claim boundary

This closes one bounded structure-level integration gap for uniaxial
bilinear steel in the 2D corotational fiber-frame path. It does not establish
a pure-steel section protocol, concrete validation, finite-strain or
multiaxial steel, local buckling, fracture, fatigue, external cyclic-member
acceptance, 3D frame breadth, production sparse/ROCm/HIP parity,
full-building equilibrium, G1 closure, or commercial readiness.
