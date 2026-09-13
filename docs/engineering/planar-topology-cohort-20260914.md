# Repeated public planar comparison across two generated connectivities

Numerical source `e534793e09c8ca7adae19212e1e687cb44c0ffaf`.
The frozen protocol extends the earlier single-story portal variants to a
two-story one-bay frame and a one-story two-bay frame. Both use 4 m bays and
3 m stories, fixed bases, the existing portal materials/sections, and the original
roof-right load vector multiplied by five. They contain respectively six and
five members, with six nodes each. These are authored development models, not
independent projects or measured experiments.

Two cases, three CPU backends and three fresh-process repetitions gave 18
predeclared slots. Backend order rotates. There were no warmups, retries,
outcome-dependent exclusions or tolerance changes. Four monotone steps retain
residual tolerance 1e-10, increment tolerance 1e-12 and a 40-iteration limit;
terminal and complete-history comparisons retain absolute plus relative 1e-9.
Each slot had a 180 s timeout.

All 18 slots entered the API, converged, passed artifact contracts and retained
eligible resource observations. Twelve cross-backend comparisons pass terminal
SI and full-history checks. Twelve same-backend repetition pairs have identical
result, validation, checkpoint and history bytes. The separate audit rechecked
461 frozen source files against current source, 180 artifact identities, input
identities, and recomputed all comparison records.

| Model | Dense median s | spsolve median s | Extended splu median s |
| --- | ---: | ---: | ---: |
| Two-story | 4.117451 | 4.134062 | 11.628921 |
| Two-bay | 3.524741 | 3.537464 | 9.813526 |

The workload includes public API validation, history reassembly and persistence;
it excludes interpreter startup and the separate parent audit. The enclosing
experiment took 167.737700 s. Individual repeat times and population standard
deviations are retained in the [machine summary](planar-topology-cohort-20260914.summary.json).
The spsolve/dense median ratios are 1.004035 and 1.003610; the extended/dense
ratios are 2.824301 and 2.784184. Neither sparse backend demonstrated a benefit
in this small generated workload. These observations do not set a general sparse
crossover threshold or establish total user-time savings.

The accepted material histories have zero steel accumulated plastic strain and
zero concrete tensile/compressive damage in both cases. Thus this adds
connectivity coverage for the nonlinear geometric execution path, **not new
yielded-material or cyclic validation**. No learned policy or training fit ran.

The immutable packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-topology-cohort-hvbomp7h`
contains the generating runner, pre-execution protocol, inputs, source snapshot,
all worker artifacts, and the separate audit. Its inventory covers 863 files /
24,827,373 bytes; inventory SHA-256 is
`16240c268463e8fae4541d7f16c1811c072c7d6c10ea6f5024dbb55830551ecb`.
Broader yielded/failure cases, independent verification, learned net benefit and
the full roadmap remain open. This is local numerical evidence for the named
source, separate from the still-running hosted CI at `b8e7c54`.
