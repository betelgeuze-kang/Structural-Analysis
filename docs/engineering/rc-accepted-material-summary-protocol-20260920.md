# Accepted material summaries: offline representation check

The cost-margin gate selected ten false positives and no true positives across
its five overlapping training complements. This motivates inspecting missing
state information, not changing the old threshold after seeing its results.

This bounded stage reconstructs all 165 existing training parents from the
pinned 99-row and 66-row inventories used by the pooled campaign. It verifies
each original context, label step, parent checkpoint and exact committed
material snapshot. Reserved evaluation cases are not solved or summarized.
No fit, numerical solve, policy promotion or runtime callback change occurs.

`rc-accepted-material-unweighted-summary.v1` contains 27 fields: minimum,
arithmetic mean and maximum of the four native steel and five native concrete
state variables. Signed plastic strain and backstress retain their signs.
All fields for every fiber must be present and satisfy native state constraints;
both material populations and an explicit matching parent hash are required.
Ordering of serialized fields cannot change the summary. Original snapshot,
parent, problem and sample identities remain separate provenance fields.

These are unweighted fiber statistics. They are not section resultants, total
dissipation, area-weighted quantities, experimental observations or independent
physical evidence. Fiber counts are reported as metadata, not input features.
Extrema and means discard spatial information and may be insufficient for
learning; no improvement is presumed.

The driver is `scripts/audit_rc_accepted_material_summaries.py`; it refuses
overwriting output. Run it from a committed frozen source snapshot. Report
complete row count, exact reconstruction, source/inventory hashes and elapsed
offline audit cost. This cost includes decoding and native reconstruction and
must not be presented as an online extraction benchmark. Concurrent numerical
work also prevents interpreting its wall time as isolated performance.

Only after this consistency check could a separately specified experiment add
these inputs to an excluded-group training table. Any eventual pre-capture
runtime integration must charge extraction, validation and decision costs even
when the policy declines. The original secant reference retains authority.

Local boundary verification: 82 tests passed in
`tests/test_rc_runtime_cost_diagnostic.py`, including 11 new summary cases.
This is local evidence only; the published 3eb50016d CI predates this code.
