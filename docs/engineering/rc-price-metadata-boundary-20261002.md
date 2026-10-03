# Declared RC prices retain the producer's metadata contract

The RC design reader accepted an empty price source when its price, request and
report hashes were recomputed. A read-only pre-change observation at
`253da5ee9cc09e45089457975b27c21641375032` returned two verified rows from that
altered report while preserving the original model, numerical result and native
checkpoint bytes. The observation executed reader code under Node 20.19.0 and
performed no numerical analysis. Hash agreement alone did not enforce the
producer's price metadata semantics. The layout reader had the same date/source
gap.

`rcPriceMetadata.ts` now supplies the metadata check to both readers. The check
matches `FiberFrameMaterialPrices` in `benchmark/fiber_frame_design.py`:

| Field | Accepted declaration |
| --- | --- |
| Currency | Exactly three ASCII uppercase letters. An official currency registry is not required by the producer. |
| Date | Exact `YYYY-MM-DD`, Gregorian calendar, years 0001 through 9999. |
| Source | A string with at least one character outside Python's `str.strip()` whitespace set and at most 1000 Unicode code points. |

Python and JavaScript differ on source length and whitespace. The shared check
preserves the producer's acceptance of 1000 non-BMP characters, a byte order
mark, a zero width space and padded nonempty text. Python whitespace-only strings,
including U+001C through U+001F and U+0085, remain invalid. An early 2000 UTF-16
code-unit bound avoids expanding a larger string; each accepted code point uses
at most two code units, so it does not narrow the producer's 1000-point limit.

Rates, quantity/estimate arithmetic, original artifact bytes, hash algorithms,
selection rules, support profiles, native solver settings, stored checkpoint
authority and existing quotas retain their contracts. Metadata is checked before
either reader exposes price-based comparison values. Declared rates still carry
no verified quote, confirmed currency saving or engineering approval.

The new registered no-solve contract file contains 41 checks. Its positive
rebind changes only valid source/date declarations and the dependent hashes,
then validates both complete design and price-order layout reader graphs. Native
originals and selected candidate identities remain unchanged. Eight negative
checks recompute the design price/request/report binding or the layout
price/plan/comparison/report graph before testing empty source, Python
whitespace-only source, lowercase currency and an impossible calendar date.
They reject specifically at `study_prices_invalid` or `layout_prices_invalid`.
The remaining checks cover the producer's accepted and rejected metadata edges
and unchanged original metadata. No solver, worker, service listener, learning
fit or research campaign runs in this file.

On the final modified local sources, the new contract file passed **41 checks in
13.8 seconds**. The same 31 metadata vectors also matched the actual Python
producer's acceptance: nine accepted and 22 rejected. This producer comparison
overlaps the frontend vectors and is not additional independent coverage.
TypeScript `--noEmit`, the static Workbench registration guard and
`git diff --check` passed. The dependency tree was reused from the retained
checkout through a temporary task-owned link; no packages were installed.
The runtime was the bundled **Node 24.19.0**, with the existing Playwright 1.56.1
and TypeScript 5.0.2. Experimental-loader and color-environment warnings remain
visible in the observed command output. A concise command/result receipt and
final changed-file hashes are retained under
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/pr-backlog-20260929/rc-readiness-goal-20261002/price/`.

The repository's pinned Node 24.20.0 frontend build and exact-final-commit hosted
CI remain unverified by this local slice. Independent physical comparison,
operational deployment, real-device latency and release authority require their
own evidence.

The separate legacy layout-control ambiguity remains open. A pure descriptor
observation with a v1 request and global DOF 7 moved control from N3 to N2 by
permuting node declarations while retaining equal context hash, descriptor
values and physical model identity. The existing canonical control/preload
binding applies to v4. A legacy fix needs an explicit compatibility scope that
preserves frozen policy contexts, such as an execution-time physical-control
guard or a newly versioned profile. This metadata correction does not alter
that context or promote old policies.
