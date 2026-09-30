# Workbench process-cost cohort v2 — 2026-09-13

Frontend source `1669647a1c4cece2f3a8635f4eb762a727c5a49e` connects the previously exported cohort v2 to Workbench.
The existing v1 format remains supported. This is integration/accounting progress;
it does not establish independent physics or learned net savings.

## Validation and presentation

The browser verifies the complete original study graph and CLI arithmetic before
reading the byte-bound process document. It independently checks exact process
fields, report/runtime identity, one observation per execution, completed exit
status, interval containment and safe integer totals. It reconstructs per-pair
process costs, outside-CLI differences, once-counted historical training and ratios,
and requires exact agreement with the supplied process accounting. Producer numeric
spelling is preserved when hashing the already-verified CLI accounting object.

A separate process-cost section shows enclosing intervals and their differences
from CLI intervals. It explicitly states that process totals replace nested CLI
times; they must not be added together. Startup alone is not inferred from the
difference. Transport, review, separate audits and campaign preparation are listed
as excluded. Incomparable pairs keep their denominator and unavailable ratios.

The worker returns original process-observation bytes for download. It retains the
existing same-origin, authorization, bounded-read and disposal behavior. V1 has no
process section or process download. Existing pinned child design review remains
unchanged.

## Executed checks

The hash-pinned Node v24.20.0 formal command
`/path/to/verified/node scripts/verify-workbench-v2-e2e.mjs --with-job-api --grep cohort --workers=1`
completed TypeScript checking, Vite build, viewer-delivery validation and **29 tests**.
This includes the 19 cohort contract tests also run separately; those 19 must not be
added to 29 as distinct coverage. New controlled cases exercise process binding,
short intervals, duplicate identities, boolean exits, wrong scope, extra fields,
changed costs and overflowing sums, plus desktop/mobile exact process downloads.
Diff whitespace checks passed. This is a filtered suite, not full hosted CI.

## Original actual-HTTP observation

The original v2 export inventory was checked against
`539c0acdbd9100b4a45e8a303c257e277c238d9bab2b89a4df388ae5098d6453`, and the
578-file snapshot was mounted through the real authorized WSGI artifact application.
No browser request interception was used.

Both 1440- and 390-pixel views retained all 4 pairs / 8 executions, showed the
process-cost section and opened selected candidate `w047`. Six downloads (cohort,
runtime and process observations per view) matched originals exactly. All 1,236
successful HTTP responses matched the source inventory, for 1,242 byte comparisons
including downloads. There were zero page errors, viewport bounds passed, and the
server exited with code 0.

The observer recorded 8051.871 ms after browser launch through
the two views, downloads, teardown and response checks. Server startup/snapshot
loading and browser launch are outside this interval. It is not a complete campaign
time and is not charged to either strategy's historical process total. No new
nonlinear solve or training fit was performed. The original two incomparable pairs
still prevent an aggregate process-cost ratio; prior scientific conclusions remain
unchanged.

## Records and remaining scope

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-process-cohort-workbench-c_p8b9zs` contains 10 files / 2,071,903 bytes; sibling
inventory SHA-256 `6ebde8c6c9243dd2b68c1982fd1d945afab27d4c8dd3d4586bbe5251cd1fdc74` binds the exact source delta,
production asset hashes, logs, observer, HTTP receipt and screenshots. Original
sealed data remain unchanged.

This closes the process-cost display/download gap documented in the preceding v2
record. Matched full campaign measurements, unseen geometry/history cases, complete
hosted CI and independent physical qualification remain open. Existing licensing,
owner/administrator and hardware dependencies remain explicit.
