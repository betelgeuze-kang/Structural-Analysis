# Paired-cost rejection reasons and development CI repair

Valid planar results could fail terminal or full-history comparison while the
paired cost fields were null and `unavailable_reason` remained null. The runner
now reports `terminal_si_mismatch`, `full_history_mismatch`, or
`worker_resources_unavailable`, in that order of precedence. Existing nested
comparison reports retain all mismatches. Valid mismatch rows remain valid;
artifact failures keep their existing separate handling. Successful pair costs
and all numerical tolerances are unchanged.

Six pairs from the original material-active experiment were replayed without new
solves. Exactly the three failing four-story reason fields changed; original
comparison values, cost values and row states remained equal. New tests cover
terminal mismatch, missing resources, precedence, and the existing middle-step
history mismatch. Backend/history tests: 162 passed. Ruff and diff checks pass.

Separately, published source 3c759fc43 development-contract job 103793727124
finished with 1 failed and 1,236 passed in 583.41 s. Its sole failure was the
workflow contract expecting 45 files after the witness and material-activity
suites expanded the selection to 47. The contract now requires 47 and explicitly
requires both new suites. Workflow/activity/witness tests: 38 passed locally.
This does not waive or satisfy the separate full-suite external preparation gate.
The repaired hosted development lane has not yet run.

Original CI log and verification summary: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-paired-cost-reason-gtwp3p8a`.
Original log SHA-256: `613f42b988fa4f289c515f575ed32ba9dc17ac7110229a98a0b53024e5053c91`.

## Exact workflow test selection verification

At local source `d6357e73b4a894e2aa48751507a26c925fbeb7b2`, the 17 pytest
selectors were extracted from the existing Workflow Contract CI command and
executed unchanged: **165 passed in 10.86 s**. This is the pytest portion locally,
not the entire hosted workflow or a fresh runner environment. The original
hosted job 103793727167 had one stale count assertion failure and 164 passes.
Both original logs are retained at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-workflow-count-repair-t3jcohyw`.
Inventory SHA-256: `e62e4e32bbfabf967f304d9e4806d7d670a03c4346c8d068adf0cdda5d71560c`.

PR 439 and issue 438 distinguish the published source from these pending local
changes. Active topology/runtime jobs were left running, and no new push was
performed during this observation. Full roadmap acceptance remains incomplete.
