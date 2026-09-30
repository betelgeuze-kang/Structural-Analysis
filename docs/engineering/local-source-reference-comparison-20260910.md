# Full comparison with an explicitly identified local source build

At product source `3848da24c8a24472c44ee622d0953c9c9cb3948e`, a fresh execution
of all **12 existing comparison cases / 94 metric rows** passes the unchanged
acceptance tolerances with the audited, arithmetic-modified OpenSees build and
pinned CalculiX packages. This expands the earlier focused reaction diagnosis to
the complete existing comparison scope. It does not replace the official wheel,
adopt a new authoritative reference, establish independent verification or close
full CI. All corresponding authority fields remain false.

## Execution identity and implementation

The new `scripts/run_local_source_reference_comparison.py` produces a distinct
`local-source-reference-comparison.v1` report. Its profile is
`local-opensees371-corot2d-rationalized.v1`; its reference label explicitly says
local build. The official receipt schema rejects this report. Both official
entry points retain their [pinned-wheel execution](opensees-runtime-binding-20260910.md).

The profile pins the [previously audited source-build packet](opensees-corot2d-arithmetic-20260910.md),
including its source revision, archive, patch, native extension, inventory and
12 dynamic-library hashes. Before execution the CLI rereads 12,126 files and
62 symlinks against that inventory. It then runs a verified private copy of the
native extension with an isolated Python interpreter, binds the actual module
origin and checks the extension and dependencies again afterward. This run uses
the existing local build; it performs no fresh compilation. Its dependency paths
are intentionally host-specific. Another build or host needs its own reviewed
profile rather than silently inheriting this identity.

Three pinned Ubuntu `.deb` packages are downloaded and verified, then extracted
privately for CalculiX. BLAS/LAPACK are copied from the verified build dependencies;
there is no system package installation. Original CalculiX inputs, DAT/FRD files,
version output and job stdout/stderr are retained, as is the OpenSees stdout,
stderr and parsed result.

The existing product calculation and acceptance logic is shared between the two
entry points. A direct AST comparison during implementation found the extracted
calculation body unchanged after substituting the local reference-name parameter,
and the extracted acceptance loop unchanged after its iterator rename. This is
a recorded development observation, not a retained raw AST-test artifact.
No tolerance, product solve, material law or accepted-result authority changes.
The optional CalculiX raw-output directory preserves the official wrapper's
default behavior when omitted.

The local report can retain failed external comparisons as failures. Its copied
case schema allows an integer external return code, while the common acceptance
validator prevents nonzero returns from being declared passing. The official
schema is unchanged. Output directories must be new, so prior packets cannot be
overwritten by a repeat invocation.

## Fresh numerical observation and record audit

| Existing case | Passing metric rows |
| --- | ---: |
| Two-DOF shear modal | 2 |
| Cantilever tip load | 3 |
| Public corotational portal path | 12 |
| Planar member-feature path | 8 |
| Planar prescribed-settlement path | 9 |
| Spatial Frame3D combined load | 10 |
| Frame3D direct axial yield | 8 |
| Frame3D cyclic axial reversal | 19 |
| Frame3D direct torsion | 3 |
| Frame3D direct bending rotations | 6 |
| CalculiX axial member | 2 |
| CalculiX tetrahedral spatial truss | 12 |

OpenSees records 35 successful `analyze` calls, plus the driver's existing modal
query. CalculiX runs two fresh jobs and its version query. All product comparison
cases are freshly calculated; 12 cases is not a count of total solver calls or
paths, since some cases contain multiple paths and internal validation work.
This observation does not independently instrument every product core/Newton
call and does not retain full product checkpoint sidecars. The report preserves
the existing metric-projection contract, not a new full-history audit contract.

A separate audit binds all 94 reference values to the retained external payloads,
parses CalculiX DAT tables independently of the production parser, and recomputes
acceptance using exact rational arithmetic on the stored floating-point values.
All 94 checks pass; the largest error-to-allowed-bound ratio is
`0.37653192143262826`. This is record/arithmetic verification by the same operator,
not independent physical validation. The parsed OpenSees result also matches its
single original stdout result exactly. All 17 report-bound raw hashes and all
219 source hashes match; the latter also match the execution commit's Git blobs.

Single local parent times, including their stated scope:

| Scope | Seconds |
| --- | ---: |
| Entire launched process | 81.541456567 |
| CLI report interval | 80.141687541 |
| Product calculations and comparisons | 76.282311525 |
| OpenSees wrapper | 0.134946594 |
| CalculiX wrapper | 0.020337904 |
| Separate record audit | 0.677506625 |
| Packet sealing and reread | 0.006801226 |

These are nested or separate intervals, not additive benchmark components.
Package download and the historical source build are outside the launched process.
No repeated timing, training fit, learned acceleration or net-cost benefit is claimed.

## Focused verification and retained packet

The final focused selection passes **46 tests, 7 deselected, in 6.11 s**. It
covers the full local-report contract, rejection by the official schema, changed
profile or runtime binding, rehashed authority and Boolean/numeric confusion,
dropped cases, raw hash mismatch, changed metrics/tolerances, invalid passing
claims and unreviewed build packets. These tests use explicit fixtures; they are
separate from the fresh numerical run above.

The first selection was 45 passed / 1 failed: the inherited official schema could
not represent a failed local external return code. The local-only schema change
and failure-claim test resolve that issue. Ruff and `git diff --check` pass. The
new CLI passes mypy using `MYPYPATH=src:scripts` with a module target and
`--follow-imports=silent`; the earlier file-target attempt had an import-resolution
error. Full repository tests and broader wrapper typing are not claimed green.
These test counts summarize completed tool output; original test logs were not
captured in this packet.

The new sealed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-source-reference-kq9c46tq`:
**30 files / 2,570,920 bytes**, inventory SHA-256
`dca428fc4a449af8f956b80ee9e1f2b456206a7f2bcca45318cbd54ca39f4d1b`.
This excludes the separately sealed, reused 638,951,334-byte source-build packet.
The new packet contains downloads, launch/process records, original external
outputs, the comparison report and audit code/results. All files are reread at
sealing; neither packet is to be appended to. The
[machine summary](local-source-reference-comparison-20260910.summary.json)
records their identities and boundaries.

No protected receipt, gap-ledger closure, official wheel, CI reference profile or
release status is changed. The official wheel's two reproduced reaction
mismatches, reference-adoption decision, same-head full CI, independent operator
verification, licensing, compatible experiments, learned net benefit and the
complete roadmap remain open. The next integration step must explicitly decide
how this separately identified local diagnostic is used without silently giving
it the official reference's authority.
