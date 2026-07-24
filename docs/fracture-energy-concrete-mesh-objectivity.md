# Fracture-energy concrete and bounded mesh objectivity

`FractureEnergyConcreteDamageMaterial` is a stateful, uniaxial crack-band
law. Its post-peak tensile and compressive branches use fracture energy and a
required characteristic band length instead of a mesh-independent strain
softening rate.

For either branch, effective crack opening and traction obey

```text
w = h * (kappa - sigma / E)
sigma = f * exp(-f * w / Gf)
```

Here `h` is characteristic length, `kappa` is the maximum absolute branch
strain, `E` and `f` are in MPa, and `Gf` is converted from N/m to MPa·m. The
implementation solves this implicit relation on its unique descending branch
and differentiates it analytically. It rejects parameter combinations for
which `h*f^2/(E*Gf) >= 1`, because the strain-to-opening mapping would not be
monotone and the selected local branch would be ambiguous.

The immutable `ConcreteDamageState` remains the accepted parent. Trial calls
cannot mutate it; tensile and compressive histories and damage are
irreversible, and failed structural Newton steps retain the parent bytes. The
reported dissipation is cohesive work minus recoverable secant-unloading
energy and approaches the declared `Gf` per crack area.

## Mesh-objectivity receipt

The generated receipt at
`artifacts/benchmarks/fracture_energy_concrete_mesh_objectivity.json` evaluates:

- traction versus effective crack opening at characteristic lengths 0.02,
  0.01, and 0.005 m;
- same-parent finite-difference tangents in tension and compression;
- a 0.04 m reinforced-concrete tension tie using 2, 4, and 8 concrete elements;
- exact prescribed-displacement paths, equilibrium, localization, fracture
  energy, deterministic state replay, and zero fallback or regularization;
- the full RC force history, with continuous reinforcement represented by one
  global parallel tie so its response is independent of concrete subdivision.

The terminal concrete element has nominal tensile strength 3.0 MPa; every
other element is 10% stronger at 3.3 MPa. This deliberately seeds one
localization band and prevents a homogeneous mesh from selecting a crack by
roundoff. It is not evidence for spontaneous or arbitrary localization.

The JSON receipt has a strict Draft 2020-12 schema, a canonical artifact hash,
and SHA-256 checksums for all numerical, schema, test, documentation, and
capability-registry inputs. Validation recomputes derived metrics and claim
gates, requires the current source set, and reruns all cases. There is no
timestamp, fallback promotion, or unbound clean-run claim.

Regenerate and verify it with:

```bash
python3 scripts/build_fracture_energy_concrete_benchmark.py
python3 scripts/build_fracture_energy_concrete_benchmark.py --check
python3 -m pytest -q tests/test_fracture_energy_concrete.py
```

This is a bounded internal candidate. It does not prove arbitrary RC frame or
shell mesh objectivity, confinement, bond slip, multiaxial behavior, published
or independent external validation, design-code authority, independent
engineering review, or release readiness.
