# Adaptive recovery completes the original short/40 mm L-frame history

Frozen source `990b30d09`, following the
[implementation and fixed-source protocol](rc-adaptive-failed-target-integration-20260921.md).
Four comparisons / sixteen paths execute the original N3 UY targets
(-20, -40, +20) mm with constant N3 FY = -25 kN. Binary64 and complete retained
arithmetic both explicitly enable terminal polishing. Two repetitions reverse
arithmetic and arm order. Native and history tolerances are unchanged.

**All four adaptive proposal paths complete all three requested targets.**
Within each arithmetic profile their complete preload/response histories and
final checkpoints repeat exactly. All twelve ordinary, secant and fresh-reference
paths remain incomplete at the first target. Thus all fresh-reference comparison
gates and qualified proposal/secant time ratios remain false/null. Completion is
not reported as a qualified speedup or independent physical validation.

Each proposal performs eighteen internal trials after preserving the failed
ordinary first attempt. The eighth internal trial fails; halving the fraction
increment passes the smaller next trial and then reaches the requested first
target. The native original-target confirmation remains authoritative. Only the
three original requested targets advance outer material history; internal trial
checkpoints are discarded as material parents.

The complete study counts **44 ordinary + 72 additional = 116 native calls** and
**168 + 426 = 594 Newton iterations**. All work is known. Summed proposal path
wall times across the two orders are 4.819358514 s for binary64 and 16.156173277 s
for retained arithmetic, including proposal/artifact work. These are raw timings,
not a cross-arithmetic speed claim or complete Workbench user-time measurement.

## Audit and retained evidence

A separate audit verifies original inventory hashes/lengths, canonical report,
path and native step hashes, report/path agreement, stage artifact references,
outer-entry parent binding, identical full parent objects within each search,
all ordinary/additional work and complete repeat comparisons. Incomplete secant
prefixes are explicitly not credited as repeated complete histories.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-adaptive-full-path-hil040y3`.
All 1,315 audited inventory entries were reread and hash/length checked.
`audited-inventory.json` SHA-256:
`ba0cd613fc2e64218720641921372497c6236ecbb6a332e39f51278e2fcf6d4c`.
[Machine-readable summary](rc-adaptive-full-path-results-20260921.summary.json).
Full raw data, source archive, predeclared plan, driver and audit remain retained.

This resolves the observed first-target obstacle in this specific example without
changing the requested history or native acceptance. Wider geometry/material
coverage, independent physics, full cost usefulness and learned net benefit
remain open. The option is experimental; existing default behavior is unchanged.
