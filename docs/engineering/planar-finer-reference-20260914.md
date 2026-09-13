# Research-only 32-to-64 concrete-layer comparison

This study follows the accepted steel-state refinement audit, which found a
1.591822% group difference between 16 and 32 layers at load factor 0.75.
It evaluates a finer discretization before interpreting numerical paths as
training or performance evidence. It does not extend the public API's 32-layer
limit, change solver defaults, or establish physical validation.

## Frozen construction and verification

Source revision: `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`.
The runner verified all source-file identities and the original 32-layer input
against the preserved source packet. It compiled that canonical model and
reconstructed each section with the existing low-level rectangular-section
builder. The 32-layer reconstruction was required to equal the original section
and complete problem. The 64-layer research problem changes only concrete
quadrature, preserving steel fibers, materials, member geometry, integration
order, loads, constraints and solver settings. Layer count and research scope
are explicit in the protocol and artifact names; this is not a public 64-layer
canonical request or an accepted public engineering result.

Both fresh paths used targets 0.25, 0.5 and 0.75, dense solution, residual tolerance
1e-10, increment tolerance 1e-12 and 40 maximum iterations. Both committed all
three steps and passed their internal contracts. The rerun 32-layer full path
object exactly equals the earlier preserved 32-layer path. Steel observations
were matched at the same member, integration point and top/bottom steel layer;
element, section and fiber trial states were checked against accepted checkpoint
states. There are 36 matched steel points per target. Concrete fibers occupy
different positions and were not matched pointwise.

## Observed differences

The predeclared exploratory screen is 1%, using the infinity norm of the group
difference divided by the finer group's infinity norm with explicit floors.
It is not a design tolerance. All reported groups passed at all three targets.

| Group | Difference at factor 0.75 |
| --- | ---: |
| Translations | 0.081175% |
| Rotations | 0.096475% |
| Support forces | 0.007085% |
| Support moments | 0.018958% |
| Steel stress | 0.145033% |
| Steel plastic strain | 0.241632% |
| Steel accumulated plastic strain | 0.241632% |
| Steel backstress | 0.241632% |
| Steel dissipated energy density | 0.241632% |

At factors 0.25 and 0.5 the steel plastic variables were zero in both paths.
Their zero difference is not evidence about yielded-state accuracy.

Single-observation core path times were 11.475226 s (32 layers) and 16.289358 s
(64 layers). These are research costs, not repeated performance measurements or
AI savings. No fitting or candidate ranking was performed.

The reduction from the earlier 16-to-32 material difference supports using the
32-layer result as a bounded approximation for this accepted prefix under the
chosen screen. The 64-layer comparator is not an exact solution. This does not
prove asymptotic convergence, concrete-history convergence, reversal behavior,
the original full factor-1 path, or any independent physical agreement. The
original high-load completion failure remains open.

## Reproduction and retained evidence

The durable packet contains `run.py`, `audit.py`, pre-run `protocol.json`, both
full path JSON files, run summary and audit. Run the retained runner with Python;
it verifies and imports the frozen source packet. Its output packet location is
written to `/tmp/structural-planar-finer-reference-root.txt`; the auditor reads
that pointer and checks the preserved earlier 32-layer result. The runner creates
a fresh evidence directory and never overwrites an earlier result.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-finer-reference-gb4lc441`

Seven payload files, 44,297,343 bytes; inventory SHA-256:
`b854315e06e54c48fc0b5d0553b4a85a8608f617b8c8a97a1afbb77ce6b54647`.
Machine-readable results: `planar-finer-reference-20260914.summary.json`.

The next full-path investigation must retain the better-resolved section and
original failure outcomes, rather than use the coarse two-layer model or relax
acceptance tolerances to manufacture completion.
