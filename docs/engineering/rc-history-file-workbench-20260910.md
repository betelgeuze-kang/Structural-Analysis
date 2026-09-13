# Workbench review of original RC history files

Source `21d8f14e0a5998ca9bfccfb43c1ab5e3a79837e6` adds **Open RC history file** in Workbench's Results section.
It opens a local `.ndjson` file produced by the
[constant-load history stream](rc-constant-history-stream-20260910.md), validates
stored records, and shows accepted preload/lateral displacements, reactions,
member forces, section responses and fiber/material states. File content is not
uploaded. A selected original step is read again on demand; material history is
read in pages of at most 20 steps. Download returns the original file after
rechecking every indexed record.

## Bounded file reading and stored consistency

The worker reads 256 KiB file slices and permits at most 16 MiB per original
record, 512 MiB per file and 4,096 authored targets. Its index contains byte
ranges and original hashes, not accumulated response bodies. The header, current
parent state and stable entity identities remain in memory. The contract test
forbids whole-file `arrayBuffer()` and verifies the bounded initial read spans on
the complete 1,010-target original. This is a read-pattern check, not a measured
browser peak-memory or arbitrary-large-model performance qualification.

Validation checks strict finite JSON, request/claim profiles, original record
hashes/order, targets, preload and checkpoint ancestry, source model identity,
constant preload loads, stored metrics and original assembly hashes. Displayed
node displacements and support reactions match the recorded global vectors;
member/section forces use the producer's original kN-to-SI convention. Fiber
strains, stresses and material states match the original assembly's trial states.
Entity identities remain consistent across records. The browser performs no
constitutive integration, equilibrium solve or model recompilation. Hashes and
self-consistent records do not authenticate the source, canonical model or
numerical implementation.

The UI distinguishes all-requested-records-present (`complete`), an accepted
prefix, and a stored rejected lateral step. `complete` describes file coverage;
it does not prove that the producer exhausted its iterator or returned a ready
execution report. Truncated JSON, missing line terminators, duplicate/reordered
records, promoted authority, incompatible physical projections and changed bytes
after indexing are rejected. A corrupt replacement clears the previous review.
Header-only or first-step failure files with no accepted response are unavailable
for physical review. No checkpoint-only restart authority is granted.

Counters describe known step calls and Newton iterations in this file. Earlier
runs, repeated work and interrupted unpublished calls require separate execution
reports, so full execution cost remains explicitly unavailable in this viewer.
This local-file consumer does not create durable HTTP job receipts or change the
existing bounded job contracts.

## Original fixture and tests

The fixture is the unchanged authored cyclic stream from numerical source
`f8dcfbb6a`, retained in the preceding sealed observation. It has one header,
one constant-load preload and **1,010 authored lateral targets**. Gzip packaging
compresses its **44,903,261 original bytes** to **4,076,451 bytes** without changing
record content. Its original SHA-256 is `6a426234f7b54ba146b8449ab4b12a4e4ce2b7740f9a4508790115e36c7be636`.
The fixture inventory identifies the source packet and original path. Creating
and reviewing this fixture performs zero new structural solves or learning fits.
It is not a public experimental reconstruction or new independent campaign.

The final production-build selection passes **44 tests in 56.4 s**, including
22 new file-reader/browser tests and existing constant and ordinary RC review
coverage. TypeScript, Vite production build, viewer delivery and diff checks pass.
The intermediate 19-reader-test passing selection overlaps those 44 and is not
added to the final count. Tests ran on the working tree subsequently committed
unchanged; 76 selected source/fixture files match the committed source snapshot.

At **1440 by 1000** and **390 by 844**, the browser opens the entire original,
selects preload and steps around/beyond the 255-target boundary through epoch
1011, verifies original displacement/reaction/fiber values, and reads steel and
concrete material pages at the beginning, middle and end. Both original downloads
compare byte-exactly. No non-GET request occurs during either local-file review.
Final screenshots are visually inspected; controls fit the mobile panel and wide
physical tables scroll within their own region. These are desktop Chromium
viewport tests, not actual mobile hardware or a deployed production service.

An initial reader test attempt has three failures because section resultants
were accessed as positional arrays; the original format has named fields. The
projection reader is corrected and all reader tests pass. An initial browser
selection passes 32 tests but two Node test workers exhaust their 4 GiB heap in
the generic deep-equality comparison of a 45 MB download. Both runs reach their
screenshots after the physical/page checks. The comparison is changed to native
`Buffer.equals`, preserving an exact byte comparison and the original memory
limits. The subsequent complete 44-test selection passes. Original browser
failure logs/screenshots are retained, and those attempts are not credited as
successful or hidden in the final duration.

## Retained evidence and open work

The packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-history-file-workbench-x153t1pr` contains 103 files / 7,516,942 bytes: selected committed
source/fixture snapshots, four built assets, initial/final browser logs and
screenshots, reader results, verification summary and the preceding hosted CI
inspection. All files are inventoried and reread exactly. Inventory SHA-256:
`eae28c661b1171de7dbc5ce31ce24c10f74b2ee19f7dbc00835012d3b320098f`. The [machine summary](rc-history-file-workbench-20260910.summary.json)
records identities, tests, scope and negative outcomes.

At preceding published head `a7f699cfcee670abb6cf8ac8c8b1dc532f728372`,
[CI 34398910777](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34398910777)
and [Repository Python Tests 34398910740](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34398910740)
finish failed. The main verify job and all four Python shard logs name
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready` before the repository tests.
The aggregate Python job also fails. Original run/job metadata and six logs are
retained. These remain unmet external prerequisites; they do not establish a new
Python assertion failure, permit bypassing the gate or prove current-source
hosted acceptance.

Full multi-invocation cost-report integration, paged durable/HTTP consumption,
experimental material/rebar/loading/sensor reconstruction, licensing and source
reuse, independent training/evaluation campaigns, learned improvement over
strong deterministic baselines, broader material/3D capability and required
independent validation remain open. The full roadmap remains active; local
consistency and browser checks grant no physical/design/release approval.
