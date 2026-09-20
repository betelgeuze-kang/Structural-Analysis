# Frozen 512-layer spatial refinement

Status: running; no convergence or physical validation claim.

The retained concrete decomposition identifies substantial fine-center versus
fine-child sampling differences at the controlling mixed-onset cells. This
motivates one full 512-layer run against the original completed 256-layer run.
Only concrete subdivision changes. The original 40 targets (2–80 mm), proportional
force vector, steel locations, material law and numerical tolerances remain fixed.
This is not constant-axial-load testing or a speed benchmark.

- Numerical source: `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`.
- Driver revision: `6ed6b1bcb`.
- Protocol SHA-256: `9e1ede09c94df2402765f8980d1c6d514dc71d87c23dc13312c7130c9e787f96`.
- New packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-512-full-refinement-og1csz_4`.
- Original 256 result SHA-256: `ae168bdad5cc4d23f0b246df39b84b1b800458033fe4ba0c9f4acaed7d98b695`.

The comparison script verifies both frozen protocols, accepted checkpoint chains,
all 40 targets and section/steel correspondence. It reports 400 nodal/steel and
240 concrete field groups, preserving the original exploratory 1% screen and
local witnesses. It uses equal-area averaging of adjacent fine concrete children.
A smaller difference is not independently verified physical accuracy; changing
witness locations does not establish asymptotic convergence order.

The shared comparison helper covers the original 128/256 and new 256/512 pair.
Synthetic tests cover both resolutions, localized projection errors, rejected
unplanned layer counts and incomplete paths. The focused file passes 52 tests;
Ruff passes. Recomputing the original retained 128/256 report with the shared
helper reproduces the entire report exactly (640 groups, zero structural solves).
No material parameter fitting or AI training is performed.

The original 34/240 concrete failures remain authoritative until the new full
path and its read-only comparison have completed. Preserve any new failed path;
do not retry with relaxed tolerances or replace the original observations.
