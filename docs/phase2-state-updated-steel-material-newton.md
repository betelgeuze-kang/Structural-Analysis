# Phase 2 state-updated steel material Newton seed

This slice adds a narrow, deterministic small-strain uniaxial steel contract.
It is a scientific kernel seed, not a general material-readiness claim.

## Implemented contract

- backward-Euler 1D return mapping;
- elastic-plastic steel with linear isotropic, kinematic, or combined hardening;
- immutable integration-point state containing plastic strain, backstress,
  accumulated plastic strain, and cumulative plastic dissipation;
- deterministic little-endian state hashes;
- same-parent trial evaluation with explicit commit or exact rollback;
- algorithmic consistent tangent checks against central finite differences;
- cyclic strain paths with plastic-flow reversals and nonnegative cumulative
  dissipation;
- a two-node bar analytic benchmark and a two-element axial-chain cyclic load
  path using `F_internal - F_external` Newton equilibrium;
- residual and increment gates, line-search history, zero fallback, and zero
  regularization in the accepted seed path.

The canonical generated receipts are:

- `implementation/phase1/release_evidence/productization/phase2_state_updated_steel_material_result.json`
- `implementation/phase1/release_evidence/productization/phase2_state_updated_steel_material_summary.json`

Regenerate them with:

```bash
PYTHONPATH=src python scripts/build_phase2_state_updated_steel_material_artifacts.py
```

Verify committed receipts without rewriting them with:

```bash
PYTHONPATH=src python scripts/build_phase2_state_updated_steel_material_artifacts.py --check
```

## Claim boundary

`state_updated_steel_seed_contract_pass=true` applies only to uniaxial
integration points, one bar, and a two-element axial chain. The receipt keeps
`material_newton_breadth_closure_claim=false`,
`g1_material_newton_breadth_claim=false`, and
`production_nonlinear_closure_claim=false`.

Concrete compression/tension damage, composite sections, nonlinear links and
springs, frame/shell integration-point coupling, published or experimental
cyclic validation, full-building material equilibrium, and production ROCm/HIP
parity remain explicit blockers.
