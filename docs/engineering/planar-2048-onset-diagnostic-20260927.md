# Retained 2,048-layer tensile-damage onset diagnostic

The saved 1,024/2,048-layer witness already decomposed the sole 1% concrete
failure at 74 mm, E3:gauss-2, coarse cell 269. This follow-up checks all 40
saved witness targets against the pinned material parameters and original
comparison. It reads a 93,748-byte witness result, an 11,624-byte input and
the committed comparison summary. It performs no structural solve, material
integration or fit, and leaves the full accepted path packets untouched.

The concrete tensile threshold is `3 MPa / 30,000 MPa = 0.0001` strain. The
history values at 74 mm straddle that threshold:

| Point at coarse cell 269 | History minus threshold (microstrain) | First positive damage target |
| --- | ---: | ---: |
| Accepted coarse midpoint | -0.109845 | 76 mm |
| Derived fine-history midpoint | -0.110977 | 76 mm |
| Accepted fine left child | -1.920567 | 76 mm |
| Accepted fine right child | +1.698613 | 74 mm |

The retained state and original frozen material law agree at every point and
target. The right child has tensile damage `0.02170039778093924` at 74 mm;
the other three values are zero. Coarse damage minus the two-child mean is
`-0.01085019889046962`. Dividing its magnitude by the **original** finer
group infinity norm `0.9999999991007982` reproduces `1.0850198900%`.
The original 1% local-field screen therefore **still fails**. At 76 mm all
four positions show damage; the witness's signed difference is then
`+0.0002853738713556875` in the saved replay. This onset timing describes
one selected cell, not all cells or an independent convergence result.

The selected derived midpoint is not an accepted solver fiber. The threshold
straddle explains why this witness is sensitive to sampling, but it does not
establish a unique cause, continuum accuracy or a correction to the solver.
The current evidence does not support changing the material law, denominator,
projection, or acceptance tolerance.

A concrete next numerical experiment is to retain the same 40 targets,
material law, loads, solver settings and complete checkpoint histories in a
4,096-layer path, then compare all 2,048/4,096 projected fields with the same
group infinity norm and 1% screen. The E3:gauss-2 cell-269 neighborhood should
be reported alongside the all-cell maximum; a local improvement alone is
insufficient. A cheaper preliminary replay at proposed quarter-cell locations
could help scope cost, but its derived fibers would not satisfy the accepted
path requirement.

Run the read-only observer with the original retained paths' small input and
witness result:

```bash
PYTHONPATH=.:src python3 scripts/analyze_planar_2048_onset.py \
  /mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-2048-witness-fixed-lx2g8vau/result.json \
  /mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-2048-full-refinement-e9q90_me/input.json \
  /tmp/new-planar-2048-onset.json
```

The [machine summary](planar-2048-onset-diagnostic-20260927.summary.json)
records the exact input SHA-256 pins, 40-target check, threshold margins,
original relative error and unchanged failure. Focused onset and existing
witness tests pass (10 tests); those tests verify diagnostic integrity, not
physical accuracy.
