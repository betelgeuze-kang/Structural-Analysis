# Full cyclic reinforcement candidate learning and search

At source `c4c364d1a1a368a0d53d6ffb7c43c157849934a3`, training,
price-order search, learned-order search and a subsequent exhaustive comparison
complete. Every result row passes a fresh complete-request solver replay and
242 transition reassemblies. Both online strategies select `small`; their frozen
rankings and numerical work are identical. This observation establishes no
learned advantage or independent physical validation.

## Frozen scope

The existing two-member RC frame retains its 242 cyclic displacement targets,
two reversals, materials, loads and explicit extended line-search request.
Only longitudinal bar area changes, with four top and four bottom bars retained.
Training areas are 0.00028/0.00036/0.00046 m². Evaluation baseline area is
0.000387 m²; alternatives are 0.00030/0.00040/0.00044 m². Physical model
identities are disjoint, but geometry and load-history families are shared.
This is one serial observation, not a project/geometry/history holdout campaign.

The SVD ridge fit uses the preregistered ridge 1.0 and no OOD margin.
Both plans are frozen before online execution; each budget includes the baseline
and one alternative. The four-model oracle runs after both online arms.
All performance limits are permissive development inputs, not code checks.

## Results and complete work

| Stage | Result rows | Attempted steps including fresh verification | Newton / linear solves | Observed elapsed |
| --- | ---: | ---: | ---: | ---: |
| Training label generation | 3 | 1,452 | 5,798 | 434.407 s |
| Price-order arm | 2 | 968 | 3,842 | 289.040 s |
| Learned-order arm | 2 | 968 | 3,842 | 289.355 s |
| Separate exhaustive oracle | 4 | 1,936 | 7,712 | 581.064 s |
| Total numerical work | 11 | 5,324 | 21,194 | See enclosing intervals below |

Rows include repeated baseline/candidate executions; they are not eleven
independent structures. Every invocation has known work. Training including
label generation costs 434.422 s; SVD fitting alone costs 0.001776 s.
Charging training once plus the learned arm gives 723.778 s versus the
289.040 s price arm. These sums exclude search preflight/CLI overhead and do
not establish a repeated speed ratio. The complete training-plus-search parent
interval is 1,597.502 s, including both arms and the separately charged oracle.
Nested intervals must not be added again to their enclosing parent.

Both online arms miss two feasible alternatives (`middle`, `large`), but neither
misses a cheaper feasible alternative. Both match the complete four-model pool
minimum: selected-minus-pool-minimum is zero. All three alternatives pass the
permissive limits; this does not demonstrate useful feasibility discrimination.

Gross concrete stays 0.84 m³. Baseline and `small` longitudinal reinforcement
masses are 85.0626 and 65.94 kg. Their common synthetic estimates are 169.0626
and 149.94, respectively. Prices are declared arithmetic, excluding transverse
reinforcement, anchorage, waste, labor and other construction costs. No actual
quotation, construction savings or global optimum is claimed.

## Audit and preserved artifacts

The audit checks 653 frozen source files against the clean source checkout,
report/plan/policy hashes and linkage, original artifact bytes, fresh replay
receipts, unchanged model fields other than bar area, quantities/common-price
arithmetic, fixed shortlists, complete oracle pool and cost-gap arithmetic.
The original runner requested `training-report.json`, whereas the trainer wrote
`training.json`. A recorded relative symlink supplies the original bytes; no
training report was edited and no training was rerun. The inventory retains
that symlink separately from regular files.

The sealed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rebar-candidate-full-103g9bv9`:
791 regular files / 773,691,049 bytes, plus the recorded alias. Inventory SHA-256:
`f3365c4198463f2e87f6541214ca137e0f0121a9bfd2624a624d9c72b4e82c20`.
The [machine-readable summary](rc-rebar-candidate-full-20260913.json) preserves
all stage costs, performance, coverage and finite-pool cost results.

This closes this bounded observation. The independent corpus, repeated split
campaigns, learned net benefit, production operation and broader roadmap remain
open. Another same-family permissive ranking repetition would not resolve the
missing independent-case or useful-discrimination evidence.
