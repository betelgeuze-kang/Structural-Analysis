# Additional same-parent quadratic cost screening — 2026-09-14

Numerical source: `ab9211f0c476b4f08e4f031ebbb8a6f51006525a`.
The earlier 20-parent screen and full-path experiment showed mixed work changes
and no demonstrated runtime gain. This follow-up observes previously unmeasured
same-parent differences over more positions, before fitting a benefit selector.
It does not rerun or relabel those earlier observations.

## Frozen scope

For each original training case train-a through train-d, freeze indices
13, 25, 37, 49, 73, 85, 97, 109, 133, 145, 157, 169, 193, 205, 217 and 229.
This is spacing 12 starting at 13 with every previously screened index removed.
The protocol and source archive are written before new numerical calls.
Use the source's existing `quadratic_seed`, without fitting or tuning. Each
experiment starts all four arms from the same original secant native parent
and complete accepted prefix. Alternate arm order, with fresh reference last.
Preserve the original retained-arithmetic profile, request and tolerances.
These original requests have **no separate constant axial preload**.

The 64 parents are from the same four already inspected related training cases.
They are not 64 independent structures, independent validation, a new held-out
campaign, or newly executed complete histories. All 64 selected positions permit
a quadratic proposal; this screen does not measure abstention overhead at reversals.

## Observed result

| Quantity across 64 parents | Secant | Quadratic |
| --- | ---: | ---: |
| Core calls | 64 | 64 |
| Inclusive linear solves | 247 | 239 |
| Newton assembly dispatches | 409 | 405 |
| Primary convergence rows | 141 | 139 |
| Sum of whole-arm intervals, seconds | 17.303123737 | 17.225825546 |

Linear solves decrease on 17 parents, tie on 37 and increase on 10. Assembly
counts decrease on only 4, tie on 58 and increase on 2. Whole-arm time decreases
on 14 and increases on 50. The 0.077298191-second aggregate difference is a
single paired observation, not a demonstrated speedup. Ordinary GitHub capture
and tool activity overlapped; this was not an isolated timing campaign.

| Training case | Secant / quadratic linear solves | Assembly dispatches | Primary rows |
| --- | ---: | ---: | ---: |
| train-a | 64 / 62 | 106 / 108 | 37 / 38 |
| train-b | 58 / 62 | 99 / 100 | 34 / 34 |
| train-c | 68 / 60 | 110 / 103 | 39 / 36 |
| train-d | 57 / 55 | 94 / 94 | 31 / 31 |

Across all four executions at every parent, 256 core calls, 1170 inclusive linear
solves and 2142 assembly dispatches were recorded. All 192 response comparisons
pass the unchanged absolute 1e-10 / relative 1e-8 checks, and all 64
reference/fresh-reference terminal checkpoints match exactly. There are zero
new fits, no policy promotion and no default solver change.

## Cost and provenance

The numerical campaign loop took 87.332498392 seconds, including per-parent
input loading and execution, excluding earlier staging/imports and later audit.
Validation took 6.166405919 seconds; through inventory readback it took
6.571246458 seconds. Those audit intervals are nested, not additive. Whole-arm
intervals already charge proposal generation, event serialization, recovery and
step IO. These are measured scopes, not a complete amortized product cost.

The auditor checks the pinned source archive and extracted bytes, original
input inventory bindings, every step/path/report hash, numerical invocation
counts and full response comparisons. It independently reconstructs quadratic
seeds using Lagrange weights, and runs the supplied-parent cost observer against
every original comparison/context. It adds no fits or numerical solves.

The [receipt](rc-quadratic-grid-20260914.json) contains per-parent results and
binds the immutable packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-quadratic-grid-4j2otjaz`.
There are 2776 files, 204627312 bytes; the adjacent `.inventory.json` SHA-256 is
`81761ff3bc436c6c4707c9a38e93dbfa17cd5e88ab1fb9607c06690a493343d4`.
Every file was reread against its length and hash before sealing.

## Decision

Do not promote quadratic extrapolation or fit a selector from these timing
signs. The wider fixed sample still has very few assembly-work improvements,
mixed case results and predominantly slower individual arm intervals. Treating
all 17 lower-linear-solve rows as useful runtime labels would repeat the earlier
mistake of replacing the product objective with a proxy. A future benefit model
needs labels that separate primary convergence, terminal work and actual costs,
with repeated measurement and campaign-level separation. This screen supplies
additional development observations; it does not itself grant training admission
or prove that retrospective per-step choices improve an evolving complete path.
