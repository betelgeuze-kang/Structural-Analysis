# Instrumented full-path assembly time on train-b

Frozen source `1aefe06d6994b5fd8a535922bc7cb510dcea7fab`; original authenticated model/request
from the existing training expansion. This is one previously inspected training
case, not an independent or repeated runtime study. Four full 242-target paths
execute reference, secant, deterministic quadratic proposal and fresh reference
in that fixed order. No new fit or learned policy is involved. Original retained
arithmetic, solver tolerances and response tolerances remain unchanged; this
request has no separate constant axial preload.

The supplement wraps the original assembly recorder and original path runner in
memory. The numerical source archive is unchanged and both wrapper definitions
are retained in run.py. Intervals include dispatch and recorder bookkeeping,
exclude the subsequent timing-list append, and cover neither linear solves nor
work outside those dispatches. Enclosing path/study intervals include all wrapper
and collection overhead. This does not compare against an uninstrumented run or
estimate instrumentation overhead separately.

All four paths complete: 968 core calls, 4,063 inclusive linear solves and 7,350
assembly dispatches. All three full response comparisons pass and the reference
repeat is exact. The auditor authenticates source/input/step/path/report bindings,
reconstructs proposal values, and verifies every per-phase timing count against
the original recorder summary. Each arm's summed dispatch time is bounded by its
full elapsed time.

| Phase | Secant calls | Proposal calls | Secant seconds | Proposal seconds |
| --- | ---: | ---: | ---: | ---: |
| primary_iteration | 478 | 488 | 12.288345 | 12.678969 |
| line_search | 236 | 246 | 6.072922 | 6.479975 |
| terminal_refinement | 480 | 482 | 12.404616 | 12.648702 |
| final_observation | 242 | 242 | 6.252869 | 6.391917 |

Secant/proposal full intervals are 61.069907 /
62.330455 seconds. Recorded assembly intervals sum to
37.018752 / 38.199563 seconds. Inclusive linear solves decrease from 870 to
863 while primary and line-search assemblies both increase by ten. Terminal
assembly count also rises by two. Thus fewer inclusive linear solves coincide
with increased measured assembly time and a 2.064% longer proposal arm in this
single instrumented observation. It does not establish a general slowdown or a
causal time attribution transferable to other machines/problems.

The result supports retaining full-cost measurements instead of using inclusive
linear count alone as a benefit label. No phase or verification is removed and
no strategy is promoted. Same-case target positions from evolving arms are not
same-parent counterfactual labels.

The campaign loop took 291.799840 seconds; the audit took
11.982522 seconds, or
12.790492 through full inventory
readback. The latter intervals are nested, not additive. Packet contains
6479 files / 430522703 bytes:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-quadratic-phase-time-hk84km8j`.
Inventory SHA-256: `fd19b10d3cdbca34e9f1bab5ce65de666548eb441248f16fb6b109a7decb9266`.
The original packet is sealed. Independent validation and the full roadmap remain
open. These results are separate from the earlier uninstrumented screening.
