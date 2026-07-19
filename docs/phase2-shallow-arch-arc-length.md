# Phase 2 shallow-arch scalar arc-length continuation

This slice adds deterministic spherical arc-length path following for one
displacement DOF and one physical load parameter. Equilibrium
`F_internal(u) - P = 0` and the spherical constraint are solved together with a
consistent 2x2 augmented Newton system.

The verification case is the exact finite-rotation symmetric two-bar shallow
arch. The path crosses its first limit point, follows the descending and
negative-load branches, and continues through the minimum-load point onto the
rehardening branch. The committed receipt records:

- 27 accepted path steps and one deliberately failed large step;
- exact accepted-state hash retention on rejection and arc-length reduction;
- no fallback or regularization;
- six centered finite-difference checks of the consistent tangent;
- first-limit load error below 1% on the accepted discrete path;
- bit-identical terminal checkpoint after midpoint restart;
- deterministic replay of the complete path and corrector histories.

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_shallow_arch_arc_length_result.json`
- `implementation/phase1/release_evidence/productization/phase2_shallow_arch_arc_length_summary.json`
- `src/structural_analysis/schemas/shallow_arch_arc_length_v1.schema.json`

Run:

```bash
python3 scripts/build_phase2_shallow_arch_arc_length_artifacts.py
python3 scripts/build_phase2_shallow_arch_arc_length_artifacts.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_nonlinear_arc_length.py \
  tests/test_shallow_arch_arc_length_benchmark.py \
  tests/test_build_phase2_shallow_arch_arc_length_artifacts.py
```

This is a narrow scalar path-following contract. It does not promote a general
multi-DOF frame/shell arc-length solver, Lee-frame coverage,
material-geometric coupling, published or experimental validation, production
ROCm/HIP parity, G1 closure, or release readiness.
