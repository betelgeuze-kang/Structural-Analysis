# Frozen 512-layer spatial refinement

Status: execution and read-only comparison complete; convergence screen still fails.

All 40 targets commit and the original accepted-path contracts pass. All 400
nodal/steel groups meet the original exploratory 1% screen. Concrete failures
fall from 34/240 in 128/256 to **27/240 in 256/512**, all tensile damage. The
maximum tensile-damage difference falls from 6.683% to **3.644856%** at 76 mm,
E2/Gauss-0/cell-129. It still exceeds the screen. No convergence, independent
physical accuracy, public API extension or release qualification is claimed.

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
unplanned layer counts and incomplete paths. The focused file passes 54 tests;
Ruff passes. Recomputing the original retained 128/256 report with the shared
helper reproduces the entire report exactly (640 groups, zero structural solves).
No material parameter fitting or AI training is performed.

The original 34/240 concrete failures remain preserved alongside the new 27/240
result; the newer observation does not erase previous measurements. Preserve any new failed path;
do not retry with relaxed tolerances or replace the original observations.

## Comparison memory handling

The 256/512 auditor reads and validates one complete path at a time. After
accepted-chain and section/fiber bindings are verified, it retains only the
comparison fields and releases the full path before reading the next result.
The full original files and hashes remain unchanged. A lifecycle regression
checks release before the second read; a failed path is rejected before feature
extraction. This avoids simultaneous retention of both full decoded paths; no
measured peak-memory reduction or streaming-parser claim is made.

## Full comparison and cost result

| Concrete field | Maximum group difference | Target |
| --- | ---: | ---: |
| Tensile history strain | 0.076290% | 16 mm |
| Compression history strain | 0.068588% | 64 mm |
| Tensile damage | 3.644856% | 76 mm |
| Compression damage | 0.856133% | 24 mm |
| Dissipated energy density | 0.745933% | 24 mm |
| Stress | 0.470767% | 70 mm |

The 27 failing tensile targets are 24, 28, and every even target from 32 through
80 mm. Compression damage now passes all 40 targets. Not every maximum decreases:
energy-density difference is slightly larger than the previous 0.710241%, and
the steel plastic-history maximum rises from about 0.028821% to 0.036067% while
remaining below 1%. Witness locations change, so these maxima do not establish
an asymptotic convergence order or uniform field convergence.

The solve takes 1,173.528013352 s, setup 0.551306872 s, and the driver through
result hashing 1,252.419510950 s (excluding final summary/inventory and audit).
These are one-run costs, not repeated speed measurements. Read-only comparison
takes 58.102399009 s; observed child maximum RSS is 9,038,968 KiB. There is no
controlled before/after memory benchmark. Packet hash verification takes
1.405419814 s separately.

All **466 payload files / 2,778,618,473 bytes** pass length and SHA-256 checks.
Fine inventory SHA-256:
`f3ecf952c9475ce4125f167c473c8b02d3edc40872faec14d1b9c22644b3b189`.
Fine result SHA-256:
`2e5974645b6f6fbc81eb8f647a9d6af049007856a466e50bc41b6f685d3fbfd3`.
Audit observer: `60e820c7d47f356a25f7a82d94c66ab861d2e38b`.
Audit packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-256-512-audit-k4uctlz9`;
all 9 files / 1,088,861 bytes verified, inventory SHA-256
`5653704a34093ae9d2acbe2be304dd5b4700bd12b1f27547c1ea9c66dfdb7b22`.
The audit executes zero structural solves and fits.

[Machine-readable summary](planar-512-refinement-20260920.summary.json) preserves
full maxima, per-field failing targets, source hashes and separate costs.
