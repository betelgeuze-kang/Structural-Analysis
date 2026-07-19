# Phase 2 state-updated concrete damage Newton seed

This slice adds a deterministic, small-strain, uniaxial asymmetric concrete
damage kernel. It is intentionally narrower than a production concrete model.

## Implemented contract

- independent tensile and compressive history variables and irreversible
  damage;
- elastic-to-peak response followed by exponential softening;
- immutable accepted material state and deterministic little-endian hashes;
- nonnegative cumulative damage dissipation;
- loading and unloading tangents derived from the same stress update;
- same-parent central finite-difference checks in both tension and compression;
- cyclic material-point history covering both damage branches;
- a prescribed-displacement one-element force/reaction benchmark;
- a two-element displacement-controlled Newton path with residual/increment
  gates, line-search history, exact rollback, deterministic replay, zero
  regularization, and zero fallback.

The canonical generated receipts are:

- `implementation/phase1/release_evidence/productization/phase2_state_updated_concrete_damage_result.json`
- `implementation/phase1/release_evidence/productization/phase2_state_updated_concrete_damage_summary.json`

Regenerate or check them with:

```bash
PYTHONPATH=src python scripts/build_phase2_state_updated_concrete_damage_artifacts.py
PYTHONPATH=src python scripts/build_phase2_state_updated_concrete_damage_artifacts.py --check
```

## Post-peak counter-evidence

The two-element post-peak solution localizes into one element. The equilibrium,
state lifecycle, and consistent-Jacobian checks pass, but that result is not
mesh-objective. The receipt therefore fixes `mesh_objectivity_claim=false`.

Crack-band or fracture-energy regularization, multiaxial damage/plasticity,
frame/shell integration points, composite behavior, nonlinear links/springs,
published or experimental cyclic validation, full-building G1 equilibrium,
and production ROCm/HIP material parity remain blockers. The receipt also keeps
`material_newton_breadth_closure_claim=false`,
`g1_material_newton_breadth_claim=false`, and
`production_nonlinear_closure_claim=false`.
