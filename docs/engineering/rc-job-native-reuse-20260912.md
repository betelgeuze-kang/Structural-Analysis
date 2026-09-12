# Native reuse in durable RC jobs and verified result display

An existing v3 RC job request can now select reuse in its execution configuration:

```json
{
  "chunk_target_count": 1,
  "maximum_api_invocations": 12,
  "reuse_line_search_assembly": true
}
```

This is the `execution_config` member of the full existing job request, not a
complete request. The optional value must be a JSON boolean; omission leaves
reuse off. Chunk/budget validation and other request requirements are unchanged.

## Binding and execution

The stored request and resume contract bind the choice. The worker forwards it
to analysis and mandatory fresh verification for every chunk. The service's
pure validators independently derive the expected API request and native scope
from the stored job request, including the reuse profile. Receipts with a
different setting cannot satisfy those bindings. Prefix replay retains the same
option when a service is reopened and a later worker claim resumes the job.

Workbench checks the boolean, API profile, native scope and every receipt before
returning `assemblyReuse: true` in its verified summary. The result panel then
shows “Intermediate calculation reuse — Enabled · same result verification
required.” Default summaries and panels retain their earlier shape/display.
The RC panel is a stored-job review view. No new submission form was created.

## Executed checks

Four actual local jobs use the existing cantilever, 600 kN constant axial load
and three authored lateral targets. Each uses real worker analysis and fresh
verification. Services are reopened between claims for split jobs.

| Reuse | Targets per chunk | Confirmed API invocations | Known core step calls | Known Newton iterations |
| --- | ---: | ---: | ---: | ---: |
| Off | 1 | 6 | 18 | 36 |
| Off | 3 | 2 | 8 | 16 |
| On | 1 | 6 | 18 | 36 |
| On | 3 | 2 | 8 | 16 |

Every job succeeds, reports no unknown work, and passes service integrity
validation. On/off pairs retain identical preload, complete response history,
terminal response and native terminal material state. Request/scope hashes
intentionally differ. Reuse reduces eligible assemblies, not these API/core
invocation or Newton-iteration counters; no job speedup is measured here.

After repairing the fixture export, 171 distinct Python tests across the four
job/contract modules pass. The first batch had 157 passes and 14 setup errors:
the new exporter attempted to read an unpublished intermediate checkpoint from
a one-chunk job. It now exports only published artifacts. The complete affected
module then passed 21 tests, seven overlapping the first batch. This repair did
not change a solver or weaken service verification. CI configuration tests add
14 passes; the constant-load durable module now runs in independent development
CI, without changing full-suite external gates.

Twelve Workbench contract tests, TypeScript `--noEmit`, Ruff, diff checks and
scoped mypy pass. Mypy also prompted an explicit null check before dereferencing
a resumed checkpoint reference; the preceding claim-consistency guard already
required that reference, so the accepted execution path is unchanged.

The current Workbench validator reads all four real job bundles successfully.
Chromium renders the reused split-job bundle at **1440×1000** and **390×844**;
the reuse label and core-call count are visible, with no page errors. Both
screenshots were inspected. Browser routes serve captured local artifacts over
a local Vite page; this is a stored-result browser test, not a production API,
authentication or deployment test. The dedicated Vite server was stopped.

## Provenance and remaining gates

Base revision `157f6e4507627dbab9c5158af043154e98b36ae8` plus captured source
changes. Fixture revision labels are repeated `a` characters, not source
attestations. Real worker execution is in-process; this does not newly establish
cross-process interruption or production lease behavior.

The packet contains four original published bundles, validator output, source
snapshots, test logs, screenshots and browser reproduction code: **44 files /
1,656,435 bytes**. Its adjacent inventory was reread and verified, SHA256
`743989fe3cbbb7237284d63a38a5c5e59e68e4285b1548ffed2cd65582e5be81`.
[The summary](rc-job-native-reuse-20260912.summary.json) records exact paths,
source hashes, test scopes and work totals.

This completes a request-to-worker-to-verified-display connection for the option.
It does not establish AI net benefit, resolve the earlier binary64 yield-case
baseline mismatch, complete hosted qualification, prove independent physics,
or grant release/owner acceptance.

The subsequent [four-geometry prefix experiment](rc-multicase-native-reuse-20260912.md)
checks native record equality and actual dispatch reduction beyond the original
single geometry. It does not establish full cyclic or learned benefit.
