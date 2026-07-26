# Fracture-energy concrete and bounded mesh objectivity

`FractureEnergyConcreteDamageMaterial` is a stateful uniaxial crack-band law.
Its post-peak tensile and compressive branches are parameterized by fracture
energy and a required characteristic band length instead of a mesh-independent
strain-softening rate.

For either branch, the effective crack opening and traction obey

```text
w = h * (kappa - sigma / E)
sigma = f * exp(-f * w / Gf)
```

where `h` is the characteristic length, `kappa` is the maximum absolute branch
strain, `E` and `f` are in MPa, and `Gf` is converted from N/m to MPa·m. The
implementation solves this implicit relation on its unique descending branch
and differentiates it analytically. It rejects parameter combinations for
which `h*f^2/(E*Gf) >= 1`, because that mapping is not monotone and would make
the selected local branch ambiguous.

The immutable `ConcreteDamageState` remains the accepted parent. Trial calls
cannot modify it; tensile/compressive history and damage are irreversible, and
failed structural Newton steps retain the parent bytes. The reported
dissipation is the cohesive work minus recoverable secant-unloading energy and
approaches the declared `Gf` per crack area.

## Mesh-objectivity receipt

The generated receipt
`artifacts/benchmarks/fracture_energy_concrete_mesh_objectivity.json` evaluates:

- traction versus effective crack opening at characteristic lengths 0.02,
  0.01, and 0.005 m;
- same-parent finite-difference tangents in tension and compression;
- a 0.04 m reinforced-concrete tension tie using 2, 4, and 8 concrete elements;
- exact prescribed-displacement paths, equilibrium, localization, fracture
  energy, deterministic state replay, and zero fallback/regularization;
- the full RC force history, with continuous reinforcement represented by one
  global parallel tie so its response is independent of concrete subdivision.

The terminal concrete element has a documented 10% tensile-strength
imperfection. This seeds one localization band consistently and prevents a
perfectly homogeneous mesh from choosing a crack through roundoff. Across the
three meshes, the generated candidate currently records a maximum total-force
history scaled L-infinity difference below `2e-11`, zero fracture-energy
spread, and terminal energy within `5e-4` of the asymptotic target.

Regenerate and verify it with:

```bash
PYTHONPATH=src python3 scripts/build_fracture_energy_concrete_benchmark.py
PYTHONPATH=src python3 scripts/build_fracture_energy_concrete_benchmark.py --check
PYTHONPATH=src python3 -m pytest -q tests/test_fracture_energy_concrete.py
```

This is a bounded internal candidate. It does not prove arbitrary RC frame or
shell mesh objectivity, spontaneous localization, confinement, bond slip,
multiaxial behavior, published Level 3 validation, design-code authority, or
release readiness.
