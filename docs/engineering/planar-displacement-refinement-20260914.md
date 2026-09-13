# Displacement-path concrete quadrature comparison

This study compares the preserved 32-layer, forty-target displacement-control
path to one fresh 64-layer low-level calculation. All targets remain 2 through
80 mm in 2 mm increments, controlling roof-right UX at native DOF 15. The whole
force vector remains proportional; vertical load is not held constant.

The frozen source is `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`. The runner verifies
all source identities and the canonical 32-layer input. For every member it
reconstructs the 32-layer section and requires exact equality with the compiled
section, then creates 64 concrete fibers while preserving the steel fibers and
material objects. Geometry, constraints, integration order and solver settings
are unchanged. The public API's 32-layer limit is not changed or bypassed by a
public request; 64 layers are explicitly a research-only low-level construction.

The pre-run comparison screen is 1%, using group infinity-norm differences
divided by the finer response infinity norm with declared floors. The auditor
matches every available accepted target and checks equilibrium/control/increment
contracts, parent checkpoint chains, element and section accepted-state bindings,
and each outer steel fiber's trial-to-accepted identity. Member and integration
locations/weights and steel labels must agree across paths. It compares load
factor, all translations and rotations, support forces/moments and steel stress,
plastic strain, accumulated plastic strain, backstress and dissipated energy.
Concrete fibers occupy different locations and are not matched pointwise.

This is a numerical discretization comparison, not an exact reference,
independent physical validation, public capability extension or evidence of AI
benefit. The forty-step displacement history differs from the previously studied
four-target load-control history. Any agreement on the earlier short prefix must
not be transferred to this longer path without measurement.

## Observations

The 64-layer path commits all forty targets and passes the unchanged internal
contracts. All forty targets match the preserved 32-layer path. The accepted
state bindings and full checkpoint chains pass the auditor. Across 400 group
comparisons, four exceed the predeclared 1% screen: four related steel internal
variables at the same 24 mm target. Thus the complete material history does not
pass the screen, despite small nodal and load differences.

| Group | Maximum difference over 40 targets | Target |
| --- | ---: | ---: |
| Translations | 0.020862% | 68 mm |
| Rotations | 0.048344% | 42 mm |
| Support forces | 0.062792% | 28 mm |
| Support moments | 0.063861% | 18 mm |
| Load factor | 0.061899% | 28 mm |
| Steel stress | 0.298969% | 68 mm |
| Plastic strain | 1.512258% | 24 mm |
| Accumulated plastic strain | 1.512258% | 24 mm |
| Backstress | 1.512258% | 24 mm |
| Dissipated energy density | 1.512258% | 24 mm |

At 24 mm, the maximum absolute plastic-strain difference is 1.292157689e-6;
the finer group's infinity norm is 8.544559259e-5. This exceeds the declared
normalizer floor, so the reported relative error is not a floor artifact. The
corresponding backstress difference is 0.006460788 MPa and the dissipated-energy-
density difference is 0.000323039 MJ/m3. These are model-state differences, not
measured error or a physical acceptance threshold. The same percentage in these
related internal variables is not four independent experimental observations.

At the final 80 mm target, the 64-layer load factor is 0.7993986519469385 versus
0.7990589271706917 for 32 layers, a group difference of 0.042498%. The internal
steel-variable differences fall to 0.041028%. Restricting comparison to that final
point would hide the earlier 24 mm discrepancy. Neither path reaches factor 1.

The single 64-layer core execution takes 162.466601 s; compilation and section
reconstruction take 0.502796 s. The experiment interval including serialization
and hashing is 173.508904 s. Source verification and the separate auditor are
outside this interval. These are numerical study costs, not a repeated speed
comparison or AI savings. The 32-layer baseline's two equal repetitions are
retained in `planar-refined-displacement-20260914.md`.

The longer path is therefore useful as a reproducible research case, while its
full steel history remains outside this numerical screen. Do not use endpoint
agreement to qualify training labels, widen the public API limit, or claim
independent physical accuracy. A further numerical reference investigation must
retain the 24 mm witness and the entire history rather than silently omit it.

## Retained evidence

Packet with pre-run protocol, runner, full 64-layer path, run summary, accepted-
state auditor and comparison audit:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-displacement-refinement-stpdjmzx`

Six payload files, 373,071,954 bytes. Inventory SHA-256:
`ae69bf84215c47170bd40b6001312533b62241acefd63390524c629be71e4a2d`.

The runner creates a fresh directory and records it in
`/tmp/structural-displacement-refinement-root.txt`. The auditor checks the saved
path identity and the original coarse path identity before comparison; it
performs no structural solve. The adjacent summary preserves all forty target
comparisons and their denominators. No training or policy promotion occurred.
