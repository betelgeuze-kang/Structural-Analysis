# Repeated material-active planar backend comparison

Frozen source `5606dac91151fc193a8f5376d592ee799837d689`. Inputs were copied byte-for-byte
from the preceding 10x-load activation screen: 3 stories/2 bays (27 free
equations) and 4 stories/3 bays (48), with 12 concrete layers and four load
steps. Dense and sparse CPU backends each ran three fresh sequential workers per
case in rotated order. No solver or comparison tolerances were changed.

All 12 paths converged and passed artifact contracts. All eight comparisons to
the first repeat of each case/backend were byte-identical. Six cross-backend
comparisons were independently recomputed from saved artifacts:

- Three-story case: all three terminal and full-history comparisons pass.
- Four-story case: all three terminal and full-history comparisons fail the
  declared fiber-stress tolerance. Material-state comparisons pass, but that does
  not override the failed stress comparison. Paired cost differences remain null.

At the last target, E13 / integration point 1 / concrete-08 has dense stress
234.9228606783097 Pa versus sparse 234.9228604035661 Pa (difference approximately
2.74744e-7 Pa). This exceeds the predeclared absolute 1e-9 / relative 1e-9
comparison at this small stress value. Both recorded strains are approximately
7.830762e-9. The observation does not establish a physical error or its root
cause; the comparison remains failed without relaxing its threshold. Repeated
byte identity shows this is reproducible within this environment.

## Costs and interpretation

| Case | Dense worker median, s | Sparse worker median, s | Qualified ratio |
| --- | ---: | ---: | --- |
| Three-story | 18.367199132 | 18.538595176 | 1.0093316375 |
| Four-story | 31.925218569 | 31.928208268 | unavailable: history mismatch |

The comparable case shows no sparse speed advantage in these three local
repetitions. Launch-through-parent-validation medians are 24.482405763 and
24.628568424 s for that case. The full experiment took 399.471296893 s, including
parent work and material-activity scanning. Per-row timing arrays, CPU and peak
RSS are retained in the adjacent summary. The four-story timings are descriptive
observations only, not equivalent-result performance evidence.

This is generated-model software/numerical evidence, not independent projects,
external physical validation, discretization convergence, learned-policy benefit,
or a release qualification. All paths retain observed concrete tensile damage;
steel plasticity was not observed. The next diagnostic must explain the small
stress mismatch before using that case for a qualified backend speed comparison.

## Retained evidence

All 461 frozen source files, input identities and 120 worker artifact identities
were verified. The failed first audit assertion was an expectation of all pairs
matching; the final auditor instead retains actual mismatches and verifies the
runner withholds paired costs. No engine outputs were edited or re-executed.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-active-repeat-izsxcjoo`.
Inventory SHA-256: `60b57ff5df7057dad625c72266f5621cc8a702d7809f06cc2ad72bcfa223c987`.
