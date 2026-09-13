# Distinguishing cost targets in the 64-parent screen

This is a read-only decomposition of the
[fixed-grid experiment](rc-quadratic-grid-20260914.md), not a new execution or
training campaign. Numerical source is `ab9211f0c476b4f08e4f031ebbb8a6f51006525a`;
the analysis was staged at `543f8a00ce1a69361fbd6a01c1131f72e04826cd`.

Of 17 parents with fewer inclusive linear solves, **14 have unchanged primary
convergence work**. Their smaller inclusive count comes from terminal linear
work. Only 6 of those 17 also have a lower observed whole-arm time. Those timing
signs are single observations; no phase-specific runtime was measured.

Only three parents have fewer primary convergence rows: train-c indices 97,
145 and 217. Each decreases primary rows by one and assembly dispatches by two;
the original screen records a lower whole-arm time for each. The observed
improvements are concentrated in one already inspected training case.

If a proposed target is specifically "fewer primary convergence rows", the
case-exclusion counts are:

| Excluded case | Fitting rows | Fitting positive rows | Excluded rows | Excluded positive rows |
| --- | ---: | ---: | ---: | ---: |
| train-a | 48 | 3 | 16 | 0 |
| train-b | 48 | 3 | 16 | 0 |
| train-c | 48 | 0 | 16 | 3 |
| train-d | 48 | 3 | 16 | 0 |

These are counts only: **no classifier was fitted**, and the rows were not
admitted as a training dataset. In the only fold containing positive evaluation
rows, the fitting set has no positive example of this target. Fitting a larger
classifier now would not supply missing cross-case evidence. This does not prove
that terminal-work reductions are worthless; it shows why primary, terminal and
whole-arm cost targets must remain distinguishable.

The same four related training cases are insufficient to claim independent
project/geometry/history generalization. The current fixed quadratic candidate
remains unpromoted. Further learning should be justified by a source-admitted
campaign with relevant benefit examples across fitting cases and an untouched
evaluation split, not by repeatedly fitting these sparse observed outcomes.

## Provenance and accounting

The script verifies original file lengths/hashes against the sealed source
inventory, validates every supplied-parent report/context through the reusable
observer, and parses every secant/proposal numerical step through the existing
iteration-cost diagnostic. For every arm it checks that primary rows plus
terminal linear solves equal the original inclusive linear count. Every delta
preserves that identity. There are zero new fits and zero new solver calls.

Aggregation took 2.697592539 seconds, excluding final result serialization,
inventory construction and sealing. The derived packet retains the runnable
script, all per-parent decompositions and input bindings:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-quadratic-targets-a0nqn869`.
Its 2 files total 114264 bytes. The adjacent `.inventory.json` SHA-256 is
`7e94212e3ab44e030500c88c1209e94c9a2c469237aced58d3ea73372670fa84`.
The [receipt](rc-quadratic-targets-20260914.json) binds this derivation and source
inventory. The original experiment packet remains unchanged.
