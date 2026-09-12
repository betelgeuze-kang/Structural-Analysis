# Actual short-history RC layout pilot

Frozen numerical source: `d6f72f0ad00a0d4c7855e760e4969fb77d52f446`.

This exploratory study addresses the missing numerical screening stage between
cost-only pruning and full-reference candidate selection. It runs original-model
prefix histories, not coarser physics, learned inference or altered tolerances.
No production multi-fidelity interface is claimed complete.

## Protocol and observations

The sealed standalone HTTP packet supplied the unchanged five-model pool, prices,
full six-target request and existing full comparison. Protocol froze prefix lengths
1 and 2 and the order baseline, small, middle, large, outside before execution.
All outcomes of this pool were previously known: this is not an independent
benchmark or unbiased policy selection. Models, materials, tolerances and request
settings are unchanged except for truncating the target suffix. Constant preload
would be retained by request replacement; this particular source request has no
constant preload, so preload execution was not tested here.

Each prefix executes analysis plus a new reference verification. Prefix rows use
the normal reference schema relative to their own saved prefix request. Their
selection flag is only a prefix screen, never full-request feasibility. The
outer pilot record explicitly retains full-history feasibility as unknown.

| Prefix targets | Models | Verified API calls | Steps | Newton / linear | Prefix call time sum | Pass prefix, fail full |
|---|---:|---:|---:|---:|---:|---|
| 1 | 5 | 10 | 10 | 20 / 20 | 3.780098961 s | baseline, small |
| 2 | 5 | 10 | 20 | 40 / 40 | 6.288194866 s | none in this pool |

At target 1 the baseline/small maximum absolute fiber strains are
1.1568488233289974e-6 and 1.489341103233409e-6, below the 2e-6 limit.
At target 2 they reach 2.3136976466579944e-6 and 2.978682206466818e-6,
which already violate that limit. Middle, large and outside pass both prefixes
and the preserved full comparison. This does not mean two targets certify an
unseen cyclic history: later reversals or larger targets can add violations.

## Verification and costs

The worker exited 0. An enclosing worker-process interval of 11.841828356 s includes
startup through exit. Prefix call sums are nested components, not additional cost.
Audit took 0.189300327 s and performed no solver calls. Preparation, sealing,
historical full paths and later UI costs are separate and not all timed.

Audit checked 642 frozen source files against their Git blob identities, 80
original artifact hash/length references, and all saved prefix requests against
the full request with only the target suffix removed. All ten prefix response
histories exactly equal the corresponding beginning of the older full histories,
including material state, reactions and checkpoint identities. Quantities and
common-price estimates also match. Older full results were bound to their sealed
inventory; they were not rerun on this head. Same-solver replay is not independent
physical verification.

No full candidate scheduler ran, no prefix checkpoint was reused for a full path,
and no fit or new training label was produced. The prefix timings alone cannot
establish end-to-end savings; running prefixes on every candidate adds costs.

## Next implementation decision

A prefix pass must remain inconclusive. A verified violation of a cumulative
history-maximum limit can motivate an explicit early rejection stage, provided
its exact model/request prefix and work are bound before deciding. Terminal-only
limits, solver failure and unknown work must not be treated as such proof.
The next comparison should execute that staged scheduler with full reanalysis for
retained candidates and charge screening, verification and remaining full work
against the existing cost-pruned baseline. Baseline handling and the frozen
candidate consideration horizon must be explicit. Workbench must distinguish
prefix-rejected, cost-skipped, fully verified and unevaluated candidates.

## Preserved packet

Root: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-prefix-pilot-07p24te7`.
753 files, 108,568,588 bytes. Inventory SHA-256:
`58a9522f2736888b6e7f159f5a7b3256e4b86ee5295819f48b60b9e8878190bc`.
The read-only packet contains launcher, frozen source, protocol, inputs, original
prefix artifacts, outcomes and audit. It does not modify earlier sealed packets.
The adjacent summary records original timings, bindings and scope. Full roadmap,
independent validation, learned net benefit and hosted acceptance remain open.
