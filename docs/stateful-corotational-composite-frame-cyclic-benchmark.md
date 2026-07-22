# Stateful corotational composite-frame cyclic benchmark

This benchmark connects steel plasticity and concrete damage to the same
two-member planar corotational fiber frame. It extends the existing 1D
iso-strain composite-section seed to axial-curvature, multi-member structure
scope without changing that seed's claim status.

## Bounded section and path

The section is a reduced-fiber, perfect-bond idealization of a steel girder and
concrete slab:

- eight concrete slab layers over a `0.60 m x 0.12 m` slab;
- two steel flange fibers and six steel web layers in a `0.30 m` girder;
- `E_s = 200000 MPa`, `f_y = 200 MPa`, and combined linear hardening;
- `E_c = 30000 MPa`, `f_t = 3 MPa`, `f_c = 8 MPa`, and independent
  tension/compression damage;
- initial transformed-section flexural rigidity `66256.81 kN m2`, split
  `71.77%` steel and `28.23%` concrete.

The strength values are deliberate benchmark inputs, not design-grade material
recommendations. Two one-metre corotational members form a straight cantilever.
A `-100 kN` reference tip load follows 60 targets: `0 -> +1 -> -1 -> +1` with
`0.05` increments on the first branch and `0.10` thereafter.

## Verified contract

The deterministic receipt verifies:

- 60 accepted steps, exact ancestry, and byte-identical replay;
- concrete tensile damage beginning at step 6 and compression damage at step
  38 after reversal;
- steel plastic evolution at steps 19 and 20 while concrete damage is active;
- separate nonnegative monotonic steel and concrete dissipation histories;
- a same-parent full-structure material-plus-geometric tangent at the mixed
  plastic/damage state and another after plastic history on the compression
  damage branch;
- pre-roundoff full-step Newton order using samples through the first
  `1e-7` relative-residual point, with terminal numerical-floor samples exposed
  rather than counted as physical convergence-order evidence;
- zero fallback, zero regularization, and exact rollback of a forced mixed
  plastic/damage failure.

Run the focused contract with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_composite_frame_cyclic_benchmark.py
```

## Claim boundary

This is one dense 2D Euler-Bernoulli, reduced-fiber, perfect-bond benchmark. It
does not model connector slip, partial interaction, composite shear transfer,
local flange/web buckling, slab fracture-energy regularization, mesh
objectivity, multiaxial material response, or rate effects. It has no external
cyclic composite-member comparison and does not establish 3D composite-frame,
production sparse/ROCm/HIP, full-building, G1, or commercial-readiness closure.
Protected readiness evidence and existing open blockers remain unchanged.
