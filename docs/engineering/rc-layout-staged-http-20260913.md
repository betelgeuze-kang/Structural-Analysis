# Staged layout graph admission and actual HTTP delivery

Admission source: `55f7f6c270b03c601b4ff5221b22aa481b1ed519`.
Original numerical source: `af3793dd3a8a34891ea81c8b76a4428c1a7ae790`.

The HTTP artifact bundle now admits staged layout plans, comparisons and reports.
It validates prefix originals and recomputes decisions before caching immutable
bytes. It performs no new numerical solve, physical replay or training. Learned
ordering still requires the existing frozen-policy prediction checks; the measured
price-only delivery below performs no prediction either.

## Admission contract

The declared prefix count is a proper nonempty prefix of the full request, with
an unchanged solver configuration, control DOF, reversal policy and constant load.
Baseline handling, no checkpoint reuse, no terminal-limit screening and lack of
full acceptance from a prefix are fixed policy fields.

Each considered candidate has an original cost decision reconstructed from prior
full verified rows. A non-baseline candidate that is not cost-skipped must have its
next prefix decision in the exact frozen order. Its original request and row have
hash/length/path bindings; model, result, checkpoint, verification and invocation
artifacts are checked against the candidate pool and request. The recorded
performance is reconstructed from original response history, including preload
when present. Cumulative-maximum violation records and action must match that
performance and the original declared limits. A prefix cannot become an incumbent
or substitute for a full accepted row.

Known-work unverified prefix records cannot carry physical screens or reject a
candidate; the full evaluation remains required. Unknown prefix work is rejected
by completed-graph admission. Extra/missing decisions, terminal-only rejection,
changed model/request, unsupported acceptance claims and omitted prefix costs are
rejected. Outcome work must equal full plus prefix work, with separate component
counts. Existing cost-pruned graph validation remains in use.

## Verification

- Existing layout HTTP tests: 98 passed in the first combined run.
- New staged tests: 63 passed after correcting a test harness method-name error;
  includes price/learned ordering, prefixes of one/two targets and 20 tampering
  variants for each graph. Changed documents are rebound through their hashes,
  so rejection is not merely an obsolete top-level checksum check.
- Repository workflow tests: 16 passed in the same corrected run (79 total,
  44.48s). The new module is explicitly registered in development CI, now 38
  selected modules. Full-suite gates are unchanged.
- Two later tests passed in 30.88s: a simulated known-work prefix verification
  failure still requires unchanged full results; an actual constant-preload
  staged graph preserves six prefix steps including verification.
- Ruff, mypy across four source modules and whitespace checks passed.

The initial combined command reported 60 failures and 101 passes in 125.59s:
all 60 failures called nonexistent `from_artifacts` in the new test harness.
They were corrected to the existing `from_reader` interface and rerun. The 101
passes include three new happy-path cases overlapping the corrected 79. Across
these commands the covered final scope is 179 distinct tests, not their raw sum.
This is focused verification, not a completed repository-wide or hosted run.

## Actual frozen-source HTTP observation

The observer read the four sealed matched-cost graphs, admitted them using the
frozen source, exported original graph bytes and served them on a loopback WSGI
server with tenant/token authorization. Every HTTP response matched its original
artifact bytes. Solver, numerical validator, fit and prediction entry points were
replaced by calls that raise if invoked. The observer exited normally and closed
the server.

| Graph | Original HTTP files | Admission interval |
|---|---:|---:|
| o0-pruned | 38 | 0.137338743 s |
| o0-staged | 52 | 0.120658296 s |
| o1-staged | 52 | 0.120069741 s |
| o1-pruned | 38 | 0.125589592 s |

All 180 responses matched. Transfer plus server teardown took 0.586132987 s,
excluding admission, source preparation, server startup and later browser review.
These small single-observation intervals are not a transport speedup benchmark.
The earlier 6.33% numerical-process observation excludes this separate delivery
work; it has not been converted into a complete user-flow acceleration claim.

Read-only packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-staged-http-485zqqlq`.
828 files, 122,973,862 bytes. Inventory SHA-256:
`a89af842412bdbd22cc99093fbf2988558d2de7800f147aef9737090804024da`.
The packet contains frozen source, observer, exported originals, receipts and
summary. Its numerical parent remains unchanged and is bound to inventory
`9a192b671d0d4c128cd6fc970d9b16ab5c9cd97a1d97ba772c7b9c4c9ebf16ea`.

## Remaining scope

Workbench does not yet read the staged schema or display/download prefix decisions.
That is the next integration step. No staged browser review, external physical
verification, independent generalization, learned benefit, hosted qualification or
full roadmap closure is claimed by this HTTP admission.
