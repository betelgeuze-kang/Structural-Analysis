# Localization of retained 64/128-layer concrete damage differences

The new read-only auditor verifies the same three original full-path SHA-256
identities used in the [cell projection study](planar-concrete-projection-20260914.md),
checks the accepted checkpoint chains, restart boundary, section/fiber bindings
and reconstructed strain locations, then measures the spatial extent of damage
field differences. No saved packet script is executed, source packet modified,
new structural solve performed, threshold changed or training example admitted.

The source numerical revision remains `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`.
All 80 original tensile/compressive group infinity differences are reproduced
exactly across the forty targets. This does not rerun the original solver at the
current code revision. The original maximum discrepancies remain failures of the
exploratory screen, even where an area-average descriptor is small.

## Results and interpretation

| Descriptor | Tensile damage | Compressive damage |
| --- | ---: | ---: |
| Original maximum group discrepancy | 12.330094%, at 74 mm | 1.937147%, at 76 mm |
| Cells above original group 1% screen at that target | 10 / 1,152 | 1 / 1,152 |
| Largest affected-cell count over all targets | 11 / 1,152 | 2 / 1,152 |
| Original witness section | E3, Gauss 0 | E3, Gauss 2 |
| Witness section mean absolute damage difference | 0.002150434 | 0.000281036 |
| Difference share from mixed-onset cells in witness section | 89.5902% | 94.1213% |
| Mixed-onset difference share across all sections at that target | 54.0255% | 65.0484% |

Damage and its absolute differences are dimensionless. A mixed-onset cell means
exactly one of its two fine children has strictly positive damage; no new damage
threshold is fitted. The group-share descriptor sums equal-area cell differences
across sections without member-length or Gauss weighting. It is not a volume
integral or dissipated-energy error. Section mean absolute difference divides by
64 equal-area cells and does not permit positive and negative errors to cancel.

The observations localize the largest discrepancy to a small portion of sampled
cells and support tracking the same spatial damage-onset neighborhood in any
subsequent refinement. They do not prove the unique cause, continuum convergence,
adequate local stress/strain resolution or physical accuracy. In particular,
small mean errors cannot replace the maximum local-error screen. A further mesh
study must retain the same load history and material model, use correspondence
across all targets and include both localized and integrated descriptors; changing
the material law to reduce this discrepancy would test a different problem.

## Reproduction and verification

Run the committed auditor against the parent directory of the three original
packets and choose a new output path:

```bash
PYTHONPATH=.:src python3 scripts/audit_planar_concrete_localization.py \
  /mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25 \
  /tmp/new-concrete-localization.json
```

It refuses changed source hashes and duplicate JSON keys, validates accepted
state chains and writes with exclusive creation. The retained full report and
exact auditor are in
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-concrete-localization-nonliw9l`:
2 payload files, 817,552 bytes; inventory SHA-256
`9f9c081a88a8fb04633bd6980bda8d02f30c17d39a2ae84862aa791a758bd5d1`.
The adjacent committed summary preserves all target-level counts and source pins.

Focused synthetic tests check concentrated error, cancellation, exact matching,
invalid damage, duplicate keys, source pins, broken parent chains, fiber binding,
strain locations and duplicate observations. Auditor and workflow contract tests
passed **31 tests in 1.88 s** (including 13 auditor checks). The new test file is
added to the development CI selection, now 61 files; full-suite coverage and
external gates remain unchanged. These tests validate audit behavior, not physics.
