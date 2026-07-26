# Bounded nonlinear transient reference

`newmark_average_acceleration_bilinear_sdof.v1` is an experimental nonlinear
transient reference used to close algorithm and state-contract gaps without
claiming a whole-building dynamic solver.

## Exact supported problem

The equation of motion is

```text
m a(t) + c v(t) + f_int(u(t), z(t)) = p(t)
```

for one displacement DOF. Input units are `m`, `s`, and `kN`; mass therefore
uses `kN*s2/m`. The restoring model is rate-independent bilinear kinematic
hardening with an immutable plastic-displacement/backstress state. The
post-yield ratio is in `[0, 1)` and zero gives perfect plasticity.

Time integration is fixed-step Newmark average acceleration
`beta=0.25`, `gamma=0.5`. Each step solves the full effective equilibrium with
the consistent material tangent. A trial material state is always evaluated
from the previous committed state, so failed Newton iterations cannot mutate
history. Nonconvergence, non-finite state, invalid tangent, or contract mismatch
fails closed; adaptive stepping, regularization, and solver fallback are absent.

## State and replay contract

Every accepted step emits a canonical SHA-256 checkpoint containing:

- model and integration-config hashes;
- absolute step/time and parent checkpoint hash;
- force, displacement, velocity, and acceleration;
- plastic displacement, backstress, cumulative plastic motion, and plastic
  dissipation; and
- cumulative external work, damping dissipation, and initial mechanical
  energy.

Resume validates the complete checkpoint before advancing. A prefix solve plus
resume produces the same checkpoint chain and terminal bytes as an uninterrupted
solve. The detached shape is defined by
`src/structural_analysis/schemas/nonlinear_transient_checkpoint_v1.schema.json`.

The solution also records equilibrium residuals and an energy-balance
diagnostic. Linear undamped free vibration conserves algorithmic energy to
roundoff. The nonlinear energy row is diagnostic rather than a promotion gate;
published cyclic and transient validation is still required.

## Verification and non-claims

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_nonlinear_transient.py
```

The focused suite covers closed-form linear free vibration, energy
conservation, analytic/finite-difference material tangent agreement, cyclic
yield/reversal, exact checkpoint resume, schema validation, tamper rejection,
cross-model rejection, and fail-closed Newton nonconvergence.

This profile is not a multi-DOF frame integrator, ground-motion/base-excitation
workflow, Rayleigh-damping calibration, adaptive time-step method, nonlinear
member formulation, external benchmark, Verification Level 3 result, or
release-ready dynamics capability.

