# Phase 2 state-updated composite section Newton seed

This slice composes the state-updated steel-plasticity and concrete-damage
kernels as a one-dimensional, perfect-bond, iso-strain axial section.

## Implemented contract

- independent immutable steel and concrete constituent states;
- deterministic composite checkpoint hashes;
- area-fraction weighted stress and algorithmic tangent;
- same-parent tangent finite-difference checks in tensile, yielded-tensile,
  and compression states;
- a cyclic path that activates steel plasticity, concrete tension damage, and
  concrete compression damage while keeping cumulative dissipation nonnegative;
- one-element prescribed-displacement force/reaction assembly;
- a two-element displacement-controlled Newton path with equal force and
  strain, deterministic replay, exact rollback, residual/increment gates,
  line-search history, zero fallback, and zero regularization.

The canonical receipts are:

- `implementation/phase1/release_evidence/productization/phase2_state_updated_composite_section_result.json`
- `implementation/phase1/release_evidence/productization/phase2_state_updated_composite_section_summary.json`

Regenerate or verify them with:

```bash
PYTHONPATH=src python scripts/build_phase2_state_updated_composite_section_artifacts.py
PYTHONPATH=src python scripts/build_phase2_state_updated_composite_section_artifacts.py --check
```

## Claim boundary

The model enforces perfect bond and common axial strain. It is not a fiber
section and does not represent axial-curvature interaction, connector slip,
partial interaction, or composite shear transfer. Multiaxial concrete,
post-peak mesh objectivity, frame/shell integration, published validation,
nonlinear links/springs, full-building G1 equilibrium, and production ROCm/HIP
material parity remain blockers.

The receipt therefore keeps `composite_section_breadth_closure_claim=false`,
`material_newton_breadth_closure_claim=false`,
`g1_material_newton_breadth_claim=false`, and
`production_nonlinear_closure_claim=false`.
