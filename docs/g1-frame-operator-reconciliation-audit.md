# G1 Frame Operator Reconciliation Audit (F2d-frame, non-promoting)

Step F2d-frame of the D→E→F plan. F2c localized the assembled-tangent /
physical-residual decorrelation to the **frame** component. This audit decomposes
the frame operator to name which frame sub-term drives the mismatch.

It is an audit only: no solver fix, no assembled-tangent change, no sparse-direct/
ILU retry, no 0.656 regeneration, no G1 promotion. Output is an untracked
`*.local.json`.

- Driver: `implementation/phase1/run_g1_frame_operator_reconciliation_audit.py`
- Tests: `tests/test_g1_frame_operator_reconciliation_audit.py` (hermetic, synthetic)
- Output: `release_evidence/productization/g1_frame_operator_reconciliation_audit.local.json`

## Method

For a random free-space direction `v`:
- `J_frame.v` = directional derivative of the force-based corotational frame
  internal force (the physical-residual frame component);
- assembled frame tangent blocks `K_frame.v`, split into `material` (a chosen
  service tangent), `geometric_delta` (axial-preload P-Delta), `elastic`
  reference, and `total = material + geometric_delta`, built under two service
  tangents: the smoke closure's `placeholder_1mpa` (1.0 MPa) and the real
  per-element `service_real`;
- each block compared to `J_frame.v` by cosine, norm, best scalar fit and scaled
  relative error, classified consistent / scale_factor / decorrelated.

## Key finding on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, reference state:

- frame share of `||J_phys.v||` = 0.9998 (confirms F2c);
- `||J_frame.v|| ≈ 3.48e12`;
- `J_frame.v` matches the **elastic** frame block with cosine ≈ 1.0;
- assembled frame **total** tangent:
  - under `service_real`: cosine ≈ 1.0, norm ratio ≈ 1.0, scaled rel error ≈ 2e-4
    → **consistent**;
  - under `placeholder_1mpa`: cosine ≈ 0.009 → **decorrelated**;
- `geometric_delta` is negligible at this reference state (norm ~8.2e3 vs ~3.5e12).

### Root cause

The F2b-ii-a / F2c decorrelation was an **artifact of the smoke closure builder
passing `service_tangent = 1.0 MPa` as a placeholder** (≈200,000x too soft vs real
steel modulus), which collapses the assembled frame material block. With the real
per-element service material tangent, the assembled frame total tangent **reconciles
with the physical residual frame JVP** (cosine ≈ 1.0, scaled rel error ≈ 2e-4).

This is a real-model reconciliation result: the production assembled tangent is
consistent with the physical residual operator at the reference state; the blocker
chain (F2b-ii-a parity fail, F2b-i preconditioner fail) traced back to the smoke
closure placeholder, not a production operator bug.

## Caveat (preserved boundary)

This consistency is shown at the `u=0` reference state, where the per-element
service tangent is ≈ elastic. At higher-load / nonlinear states the service tangent
(`solver_tangent_mpa`, the regularized/reduced value named by the D audit) will
diverge from elastic — that material-reduction question is separate and remains open
for nonlinear states.

## Next slice (F2e)

Rebuild the smoke closure (F2a builder) with the real per-element service material
tangent instead of the 1.0 MPa placeholder, then re-run the F2b-ii-a sparse-direct /
ILU direction solve at the reference state — now expected to reconcile and yield an
accepted alpha. Still non-promoting; 0.656 continuation (F2b-ii-b) remains deferred,
and the nonlinear-state material reduction remains a separate question.
