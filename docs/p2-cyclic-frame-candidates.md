# P2 cyclic corotational frame candidates

Four existing benchmarks execute material history inside actual two-member
planar corotational fiber-frame assemblies:

- steel-dominated sections compare isotropic, kinematic, and combined
  hardening through reversal;
- concrete-dominated sections track asymmetric tension/compression damage and
  nonnegative dissipation;
- perfect-bond composite sections combine steel plasticity and concrete damage
  in one section; and
- two elastic-carrier columns isolate a stateful bilinear transfer link,
  compatibility, and force scatter.

Each benchmark uses the same committed parent for material and geometric
tangents, deterministic Newton commits, state hashes, nonnegative cumulative
dissipation, yielded reversal, and a deliberately forced failed step whose
member/link state rolls back exactly. The four focused modules contain 31
tests.

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_steel_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_concrete_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_composite_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_linked_frame_cyclic_benchmark.py
```

These are repository-generated bounded benchmarks. They do not establish
published material cyclic validation, fracture-energy regularization in a
frame, confinement or bond-slip member integration, partial composite slip,
3D cyclic response, local buckling, external device acceptance, or release
authority. Their tangent finite-difference acceptance uses the declared
scientific tolerance; a single platform-specific last-digit fingerprint is not
treated as engineering evidence.

