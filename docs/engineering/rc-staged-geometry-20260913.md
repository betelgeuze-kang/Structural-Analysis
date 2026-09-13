# Staged candidate screening on two new L-frame geometries

Frozen source: `0efd85afdfe33314c70fcfdc26802d81159e0bc0`.
The preceding [nonlinear staged campaign](rc-layout-staged-nonlinear-20260913.md)
kept one geometry while changing displacement amplitude. This observation changes
the vertical member from 2 m to 1.5 m or 2.5 m, retaining the 2.5 m horizontal
member, materials, reinforcement/section alternatives, loads and supports.
The five-model pool is regenerated for each geometry, including a fresh baseline;
quantities and common synthetic estimates follow the changed lengths.

Both cases retain the six-target cyclic request with maximum absolute displacement
0.02 m and declared maximum absolute fiber-strain limit 0.003. The two-target
prefix, budget of five and price-order strategies were fixed before any new solve.
All twelve slots were scheduled in advance: pruned/staged, staged/pruned and
pruned/staged per geometry. Thus order is varied but not evenly balanced. No fits,
new training labels, automatic retries or outcome-based exclusions occurred.
These are related generated structures, not independent projects or experiments.

| Vertical member | Selected in all six runs | Staged/pruned process ratios | Ratio of time sums |
| --- | --- | --- | --- |
| 1.5 m | middle, estimate 219.78138 | 0.953644 / 0.973483 / 0.963588 | 0.963561 |
| 2.5 m | middle, estimate 272.91534 | 0.954315 / 0.956848 / 0.957390 | 0.956180 |

The observed reductions are about **3.64% and 4.38%**. All paired outcomes were
comparable under the frozen rule: the same verified eligible candidate and
estimate in both modes. Estimates are declared synthetic material values, not
quotes or actual currency savings. Three repeats on one non-isolated host provide
ranges, not independent-case confidence intervals or general performance claims.
There is no learned policy in these decisions.

Per pruned execution there are three full rows, six API invocations and 36
attempted steps. Per staged execution there are two full rows plus two prefix
rows, eight API invocations and 32 attempted steps. Newton/linear counts are
218 versus 208 for the short geometry and 220 versus 210 for the tall geometry,
identical across their respective repetitions. Screening increases invocation
count while avoiding part of a full path; invocation count alone is insufficient
to measure its benefit. Known-work checks found no unknown solver attempts.

All twelve processes completed without timeout or failure. Across them, 30 full
rows passed complete internal fresh-reference verification and showed nonzero
steel plastic strain or concrete tensile damage. Twelve prefix rows passed their
own reference verification; only full verified rows could become selections.
Twenty-four repeated full records matched in request, complete response history,
terminal response and checkpoint. All twelve prefix histories matched the
corresponding full-history prefix. This is same-solver consistency, not external
physical validation, global pool optimality or design approval.

The audit admitted 540 original graph artifacts, checked frozen source/input
hashes, reconstructed the exact geometry edits and checked selections, material
quantities, common prices, decisions, work and original physical-record bindings.
Generated input files carry a terminal newline; exported canonical models omit
that newline, and this explicitly checked difference is not reported as raw-file
identity. The audit ran no Newton solve or training fit.

The parent campaign took 178.440414886 s. Each comparison time encloses a fresh
Python process from launch through exit, including original record persistence.
Preparation, subsequent audit (3.789215786 s), HTTP and Workbench remain outside
those paired intervals. BLAS/OMP/MKL worker thread counts were one; the host was
not isolated. The original scripts, inputs, frozen source, outputs, audit and
inventory are retained read-only in the packet identified by the
[machine summary](rc-staged-geometry-20260913.summary.json). Earlier packets are
unchanged. No raw source or evaluation packet was added to training.

This extends the bounded deterministic scheduling observation to two declared
geometry variants. Other histories, limits and structural families may make
screening slower, as an earlier amplitude case already did. Learned net benefit,
independent physics, end-to-end user costs, current-head hosted qualification and
the complete roadmap remain open.
