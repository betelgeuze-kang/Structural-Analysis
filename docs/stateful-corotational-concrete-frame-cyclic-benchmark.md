# Stateful corotational concrete-frame cyclic benchmark

This benchmark connects the existing small-strain asymmetric concrete-damage
law to the accepted-state corotational fiber-frame Newton path. It is a bounded
internal material-breadth case, not an external cyclic-member validation or a
mesh-objective fracture model.

## Case

The model is a two-member planar cantilever:

- nodes at `(0, 0)`, `(1, 0)`, and `(2, 0)` m;
- the first node is fixed in all three planar DOFs;
- a `-100 kN` reference vertical load acts at the tip;
- each member uses three Gauss points and eight concrete layers;
- the load-factor history rises to `+1`, reverses to `-1`, and returns to
  `+1` in 30 accepted targets.

The section protocol requires both concrete and steel fibers. Two elastic
reinforcement layers therefore use `E = 200000 MPa` and an intentionally
unreachable `1e12 MPa` yield stress. They stabilize the post-cracking
load-controlled path without plastic dissipation. The initial flexural-rigidity
split is:

```text
concrete       EI = 31500 kN m^2
reinforcement  EI = 10240 kN m^2
total          EI = 41740 kN m^2
concrete fraction = 0.7546717777
```

The case is therefore described as **concrete-dominated with elastic
reinforcement stabilization**, not as a pure-concrete section.

## Asymmetric damage law

The material keeps independent nonnegative tension and compression history
variables:

```text
kappa_t,n+1 = max(kappa_t,n, max(epsilon, 0))
kappa_c,n+1 = max(kappa_c,n, max(-epsilon, 0))
sigma = (1 - d_active) E epsilon
```

Beyond each strength threshold, the surviving stiffness fraction follows the
existing exponential law. Damage cannot decrease, unloading uses the damaged
secant stiffness, and every accepted damage increment adds nonnegative
dissipated energy. The benchmark uses the existing defaults:

- `E = 30000 MPa`;
- tension strength `3 MPa` and softening rate `3000`;
- compression strength `30 MPa` and softening rate `400`.

These are bounded algorithmic parameters. They are not an experimental
calibration or a crack-band regularization.

## Independent elastic prefix

The first load factor is `0.1`, so the elastic reference load is `10 kN`. Its
tip displacement is checked against

```text
v_tip = P L^3 / (3 EI)
```

with a relative tolerance of `1e-6`. The observed relative error is about
`9.41e-8`; no concrete damage or steel plasticity is active at that step.

## Cyclic state observations

The deterministic path records the following internal observations:

- first tensile-damage evolution at step 2;
- first compression-damage evolution at the positive peak, step 10;
- compression-damage evolution on the reversed face at the negative peak,
  step 20;
- final concrete state count `48`, with `48` tension-damaged and `2`
  compression-damaged states;
- maximum final tension damage about `0.99998935` and compression damage about
  `0.18849700`;
- final structure dissipation about `0.000349563 MJ`;
- zero accumulated reinforcement plastic strain and zero reinforcement plastic
  dissipation.

Every concrete state is compared to the same ordered state in its parent
checkpoint, not just through an aggregate maximum. Both damage variables must
remain componentwise irreversible. Total section dissipation must be
nonnegative and monotonic, and it must increase after reversal.

## Stateful nonlinear contract

Every Newton trial starts from one immutable accepted frame checkpoint. The
free-equation residual and tangent are

```text
r(q, lambda) = F_internal(q; state_n) - lambda F_reference
K_consistent = K_material + K_geometric
```

At step 10, where both tension and compression damage evolve, every free
Jacobian column is checked by a central difference from the same parent
checkpoint. The measured relative infinity-norm error is about `8.27e-9`. The
check also requires active material and geometric terms, tangent symmetry,
exact decomposition, damaged members, and zero yielded members.

The first damage step supplies a full-step local Newton convergence window with
minimum observed order about `1.91`. Every accepted step records the residual,
iteration count, line-search history, damage increments, checkpoint hash, tip
displacement, and dissipated energy. The full path is replayed and must produce
the same receipt and final canonical checkpoint bytes. Fallback and
regularization counts remain zero.

A forced `max_iterations=0` attempt starts from the accepted `lambda=0.9`
boundary and targets `lambda=1.0`. Its trial response evolves damage in both
members, but the solver returns the exact parent checkpoint bytes and does not
claim convergence.

## Run

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m pytest -q \
  tests/test_stateful_corotational_concrete_frame_cyclic_benchmark.py
```

The reusable entry point is
`build_stateful_corotational_concrete_frame_cyclic_benchmark` in
`structural_analysis.benchmark`.

## Claim boundary

This closes one bounded structure-level integration gap for uniaxial
asymmetric concrete tension/compression damage in the 2D corotational
fiber-frame path. It does not establish a pure-concrete section, mesh
objectivity, crack-band or fracture-energy regularization, multiaxial concrete,
external cyclic-member acceptance, 3D frame breadth, production sparse/ROCm/HIP
parity, full-building equilibrium, G1 closure, or commercial readiness.
