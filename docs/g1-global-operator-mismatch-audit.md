# G1 Global Newton Operator Mismatch Audit (non-promoting)

This audit **names the operator** that the current G1 direct-residual Newton
corrector actually uses, and contrasts it with the Jacobian of the physical
residual. It is a diagnostic that makes the next implementation step (an opt-in
physical-consistent operator) safe. It is **not** a fix and **not** a closure.

- Driver: `implementation/phase1/run_g1_global_operator_mismatch_audit.py`
- Tests: `tests/test_g1_operator_mismatch_audit.py` (hermetic, synthetic fixtures)
- Output: `release_evidence/productization/g1_global_operator_mismatch_audit.local.json`
  (untracked `*.local.json`; never promoted, never committed)
- Current frontier tracked audit:
  `scripts/build_g1_current_frontier_operator_mismatch_audit.py` writes
  `implementation/phase1/release_evidence/productization/g1_current_frontier_operator_mismatch_audit.json`
  from the full-load HIP step16 no-descent receipt. This tracked audit is also
  non-promoting; it records that the current scaled global-Krylov plus
  current-tangent row-correction operator family produced no residual descent at
  `load_scale=1.0`.

## Non-promoting guarantees

- `is_audit_only: true`, `promotes_g1_closure: false` in every payload.
- Derived only from already-emitted, non-promoting local probe/tangent reports;
  it does not run the solver, change the solver, or regenerate tracked evidence.
- The current frontier tracked audit is likewise derived only from already
  emitted productization receipts and does not run the solver.
- Preserves all partial/proxy/external-blocked evidence boundaries.

## What the audit fixes in machine-readable form

1. **Normalization factor is named.** The linear-correction direction uses a
   solver-only damping `normalization_lambda` (~515) that is explicitly excluded
   from the physical residual (`direct_residual_uses_solver_regularization=false`).
2. **Corrector scaling differs from the physical residual operator.** The frame
   service-material tangent is reduced far below elastic (min ratio observed
   ~4.8e-6 over ~1763 elements) and combined with the lambda damping, so the
   Newton direction is not `dR/du`.
3. **Shell/surface material tangent is elastic/passive at the checkpoint**
   (zero nonlinear surface rows, min tangent ratio ~0.999, max abs strain
   ~2.6e-6). The shell material tangent is therefore **not** the stall driver.
4. **Alpha scan reproduces "only an infinitesimal step is descent."** The
   recorded trust-region candidate rows show the residual decreasing only for
   `alpha <= ~1.25e-4`; any productive step increases the residual. The
   directional-Jacobian predicted residual change exceeds the physical residual
   by up to ~8.3e5x.

## Named conclusion

The current corrector is `current_normalized_frame_geometric` (service-material
reduced frame tangent + geometric delta + lambda damping). The stall driver is
this regularized/reduced frame+geometric operator, **not** the shell material
tangent and **not** GPU/HIP residency. A future opt-in
`physical_consistent_frame_shell_material_geometric` operator must be added
behind a feature flag and validated against the physical residual before any G1
gate is considered.

The current full-load frontier audit keeps the same boundary but updates the
frontier: `g1_current_frontier_operator_mismatch_audit.json` records
`full_load_no_descent=true`, global Krylov best residual
`5.572699041492692 N`, current-row best residual `5.58261631268956 N`, and
`next_required_operator=physical_consistent_frame_shell_material_geometric_with_state_updated_material_tangent_and_full_residual_globalization`.
