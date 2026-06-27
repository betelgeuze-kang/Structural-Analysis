# G1 Component Operator Reconciliation Audit (F2c, non-promoting)

Step F2c of the D→E→F plan. F2b-ii-a found the assembled free-space tangent is
decorrelated from the physical residual directional derivative
(`cosine(K.v, J_phys.v) ≈ 0.02`). This audit decomposes `J_phys.v` component by
component and ranks which component drives the decorrelation, so a later slice can
adjust only the offending component.

It is an audit only: it does not modify the solver, does not promote G1, does not
regenerate the 0.656 continuation checkpoint, and writes only an untracked
`*.local.json`.

- Helpers: `implementation/phase1/g1_operator_component_audit.py`
- Driver: `implementation/phase1/run_g1_component_operator_reconciliation_audit.py`
- Tests: `tests/test_g1_component_operator_reconciliation_audit.py` (hermetic, synthetic)
- Output: `release_evidence/productization/g1_component_operator_reconciliation_audit.local.json`

## Method

For a random free-space direction `v`:
- `J_phys.v` = matrix-free physical residual directional derivative;
- `K_total.v` = assembled free-space tangent action;
- per-component `J_c.v` = directional derivative of each physical internal-force
  component (frame / spring / shell_membrane / shell_bending_drilling /
  material_stress_correction), via `include_component_forces`;
- per-component norm, cosine with `J_phys.v`, contribution ratio; mismatch
  classified as `consistent` / `scale_factor` / `decorrelated_not_scale_factor`;
- spring tangent (`K_spring.v`) cross-checked against the spring residual JVP
  (spring internal force is linear `K_spring @ u`, so they must agree).

## Observed on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, reference state:

- global `cosine(K_total.v, J_phys.v) ≈ 0.020`, `||J_phys.v|| ≈ 3.48e12`,
  `||K_total.v|| ≈ 6.46e10` (decorrelated, ~54x magnitude gap);
- component reconstruction is exact (`sum(J_c.v)` vs `J_phys.v`: cosine 1.0,
  rel error ~7e-17);
- **frame** carries 99.98% of `||J_phys.v||` (norm ~3.48e12) and is aligned with
  `J_phys.v` (cosine 0.9998);
- shell_membrane ~1.8% (cosine ~0.02), shell_bending_drilling ~0.6%; spring and
  material_stress_correction non-contributing at this state.

### Ranked suspect: `frame` (priority 1)

The physical residual's directional derivative is essentially the **frame**
component (force-based corotational internal force, `quasi_tangent_k_eq_at_u`
model), which the assembled tangent fails to reproduce in both magnitude (~54x)
and direction (cosine 0.02). Springs (linear `K_spring @ u`) and shell are not the
drivers.

## Next slice (per F2c case taxonomy: Case 2/3 — frame)

Reconcile the force-based corotational frame internal-force linearization with the
assembled frame tangent: force-based frame internal force vs geometric/material
tangent, geometric (P-Delta) stiffness sign and load scaling, service-material vs
physical material tangent, and any unit/scale conversion in the force-based frame
fastpath. This must be resolved before any sparse-direct/ILU retry or F2b-ii-b
continuation work.

## Not done here

No solver fix, no assembled-tangent modification, no sparse-direct/ILU retry, no
0.656 continuation regeneration, no G1 promotion.
