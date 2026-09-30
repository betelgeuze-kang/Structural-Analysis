# Fixed full-history 2,048-layer observation protocol

The completed 512/1,024 comparison still fails fourteen of 240 concrete groups. The next single observation doubles concrete layers to 2,048 and compares against the original 1,024-layer path, preserving all forty targets from 2 to 80 mm, DOF 15, geometry, reinforcement, material parameters, solver defaults and the proportional force vector. This is not constant axial loading. No retries, tolerance changes, group exclusion or threshold tuning are planned.

Numerical source remains `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`, validated against all 461 original manifest entries and Git blobs. Input SHA-256 remains `34822feaee8f569712b46e5842f5fcc3253a9a851bb9a13c92624be238b4c23e`. The generated 2,048-layer protocol must hash to `6508da674654590141a1b4084b9f59069a70db834da8c4070be153f0dccf9e43` before the solver starts.

The coarse original full-result hash is `2f923d7537b4ddf10ce19e0959fd081767466442e9f438ef1265c7461154446b`; its protocol hash is `e620f118fc72a7af34b8a527649dcddc3d1b78902922aab2860baa92ba73432b`. Reuse the [verified complete coarse comparison features](planar-bounded-reader-results-20260920.md), SHA-256 `bc7e6b6666bcc6104ceb9fed33af6039db7a53827c2c71c2d9919951359c119a`, bound to verification inventory `8b2333e4e1c55200425444516d08786cd1550e715c5d4d04b0f754b9960fdce2`. The auditor checks this fixed provenance and forty-target coverage.

Fine output uses the byte-preserving stepwise writer and retains both complete JSON and step files. Fine verification checks their complete-byte relationship and accepted checkpoint chain through the bounded reader. The audit keeps the original 400 nodal/steel and 240 concrete group comparisons, local maxima/witnesses and exploratory 1% screen. The source and full-size evidence for this storage change are linked in the [round-trip](planar-path-roundtrip-20260920.md) and bounded-reader reports; neither changes solver authority.

## Resource and verification scope

Preflight available resources: approximately 27.6 GiB RAM and 214 GiB free disk. Require at least 12 GiB available RAM and 40 GiB free disk before launch. The 1,024-layer full-result/step-copy packet occupies about 10.7 GB; roughly doubling that output is a planning estimate, not a measured 2,048-layer size. The bounded 1,024-layer reader peaks at 967,700 KiB, while a future larger step and retained feature arrays will need more memory. Original solver-path objects remain in memory, so no exact peak is promised.

The 1,024-layer solve took 2,305.99 s; roughly twice that plus output/audit work is a planning estimate, not a speed claim or timeout-based failure rule. Observe the live process and recorded resources. Do not restart a completed solve to fix reporting; preserve failures and continue read-only recovery if needed.

Focused checks pass 91 tests in 2.48 s, including 1,024-cell projection witnesses, rejected unplanned resolutions, pinned coarse-feature receipt/digest checks, protocol mismatch rejection, and existing step-writer/reader controls. The actual coarse feature payload loads with all forty targets, eighteen sections and 1,024 cells per section. Ruff and diff checks pass. Public API scope is unchanged.

The [completed observation](planar-2048-refinement-20260920.md) passes all 400 nodal/steel groups but retains one of 240 concrete failures: tensile damage at 74 mm differs by 1.0850199%, above the unchanged 1% screen. This does not establish continuum convergence, independent physical validation, sparse performance, broader topology/material/3D scope or release readiness. Those original roadmap requirements remain open.
