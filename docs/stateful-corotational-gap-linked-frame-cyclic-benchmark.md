# Stateful corotational compression-only gap-linked frame benchmark

## Implemented boundary

This benchmark couples the free top global `ux` DOFs of two independent
three-metre corotational fiber cantilevers with one frictionless scalar gap.
The columns reuse the deliberately high-strength elastic carriers from the
bilinear-link benchmark so the unilateral active set can be isolated.

For node order `i -> j`, the physical deformation and signed clearance are

```text
delta = ux_j - ux_i
c     = delta + g
```

where `g >= 0` is the initial gap. The link law is

```text
c >= 0: F = 0,   kt = 0       (open, including exact closure)
c <  0: F = k c, kt = k       (closed in compression)
```

Compression is negative. The force is continuous at `c = 0`; the derivative
is not unique there, so the declared one-sided algorithmic convention selects
the open tangent. Finite-difference checks are evaluated strictly inside the
open and closed branches, never across that kink.

The immutable gap state stores the active-set bit, maximum penetration, and
closure/opening event counts. These fields do not introduce plasticity or
dissipation: response remains elastic and memoryless, while the state provides
deterministic checkpoint, restart, replay, and rollback metadata. Definition
and state types must match exactly.

## Deterministic path and checks

The reference right-top load is `20 kN`, the gap is `0.004 m`, and the closed
contact stiffness is `5000 kN/m`. A 30-target path crosses the contact boundary
twice and returns open:

- active steps: `6-14` and `22-28`;
- closure transitions: steps `6` and `22`;
- opening transitions: steps `15` and `29`;
- final closure/opening counts: `2/2`;
- maximum penetration: `0.0014993474415900248 m`;
- final recoverable contact energy: exactly zero.

The small-displacement cantilever stiffness predicts first contact at load
factor `-0.18207222222222222`, bracketed by the open `-0.15` and active `-0.2`
targets. At load factor `-0.3`, the two-column/contact closed-form force is
`-1.080878777309031 kN`; the corotational result is
`-1.0808740768629466 kN`, a relative difference of
`4.348726409507784e-06`. The open-branch relative-displacement difference is
`3.483666412349666e-07`.

Same-parent finite differences report:

- open full frame-plus-gap tangent relative error:
  `1.1152785642999115e-08`;
- closed full frame-plus-gap tangent relative error:
  `2.1366444859935052e-08`;
- open material tangent error: exactly zero;
- closed material tangent relative error: `4.5511114876717325e-12`;
- link geometric tangent: exactly zero because `delta` is linear;
- frame geometric tangent remains active.

All 30 targets commit without fallback or regularization. The maximum residual
is `3.098188769929879e-10 kN`, maximum force-transfer/balance error is
`3.994280461938615e-10 kN`, and compatibility is exact. Repeated execution is
byte-identical, common global translation preserves open and closed response,
and a forced Newton failure retains both the frame and active gap parent bytes.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_gap_linked_frame_cyclic_benchmark.py
```

The test covers material validation, active-set event invariants, exact-closure
tangent selection, public API exposure, open/closed scatter, mixed state/type
rejection, analytic open/onset/closed branches, same-parent tangents,
deterministic replay, exact rollback, and JSON-safe claim serialization.

## Claim boundary

The receipt status is `partial`. It verifies only one planar, frictionless,
elastic, scalar global-x compression gap with a fixed node-order normal. It is
not a local or follower contact normal, friction, impact, restitution, coupled
contact, general foundation uplift validation, inelastic contact, member hinge
or shell contact integration, an external contact acceptance result,
production sparse/ROCm/HIP execution, full-building equilibrium, G1 closure,
or commercial-readiness evidence.
