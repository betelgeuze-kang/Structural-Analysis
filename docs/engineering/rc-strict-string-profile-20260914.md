# Strict JSON string scan: profiled consumer optimization

Baseline source `5a0def37655a095c2bd25028b0be74142a6eebe2`; the receipt retains
the exact parser/test patch and rebuilt worker bundle for the changed observation.
No numerical model, solver tolerance or artifact-authority rule changes.

## Measured cause and implementation

A Chromium CPU profile of the actual search worker reading the existing 525 MB
candidate graph identified raw JSON slicing, hashing and strict string scanning
as substantial sampled functions. In the baseline, strict scanning individually
JSON-decodes every string token, although only decoded object keys are needed
for duplicate detection and the whole document is JSON-decoded at the end.

The parser now returns already-scanned unescaped keys directly and only invokes
individual JSON decoding for escaped keys. Value strings are fully scanned for
valid escapes and control characters without producing an unused decoded string.
Final whole-document JSON decoding remains. Escaped key aliases still participate
in duplicate detection; invalid escapes and unescaped control characters remain
rejected. This removes redundant decoding without adding a cache or changing
per-request authorization, original-byte hashing or semantic validation.

Two new regression tests exercise plain/escaped/Unicode/surrogate keys and values,
escaped duplicate aliases, all 32 unescaped control characters in keys/values,
invalid Unicode escapes and unterminated strings. The four selected native-frame,
RC job/design/search contract files pass 112 tests in 21.1 seconds. TypeScript,
production build and viewer delivery also pass.

## Actual full-data observations

Both baseline and changed builds serve the existing 75-artifact, 525,181,454-byte
snapshot through the actual authenticated HTTP fixture. A desktop 1440px test
verifies the panel, settings, selection, original downloads and layout. Each run
passes, with all 79 HTTP responses matching original byte lengths and SHA256.
The fixture records zero added solver calls and fits. No route interception is
used for this successful observation.

| Instrumented observation | Baseline | Changed |
| --- | ---: | ---: |
| Navigation to verified panel, ms | 16,491.680244 | 15,355.652433 |
| Worker CPU samples | 14,845 | 13,847 |
| Strict string function sampled self intervals, ms | 2,910.276 | 1,719.693 |

These are one ordered instrumented run per version. Profiling overhead, scheduling
and cache effects are not isolated. Sample intervals are sampling estimates, not
exact per-function CPU accounting. Worker attachment starts after target creation,
so the profile may omit startup work. This is not repeated user-latency evidence,
a guaranteed speedup, numerical acceleration or physical verification.

An initial profiler harness incorrectly filtered new worker targets by URL before
the URL was populated. The panel reached verified but the profiling assertion
failed with zero profiles, before later download assertions. That failed packet
is retained. The corrected harness attaches to the created worker by target type;
recorded sample URLs identify the actual search-worker bundle. It does not retry
or alter a failed solver path.

## Evidence and remaining scope

The [receipt](rc-strict-string-profile-20260914.json) binds baseline/changed CPU
profiles, actual HTTP receipts, original bundle/parser sources, exact patch,
runners, build/test logs and the initial failed harness. All four inventories
are reread before sealing outside default Playwright output. No original numerical
packet is changed. The receipt's source head is the published baseline, not a
claim that hosted CI has validated the pending parser change.

Repeated comparable latency/memory measurements, mobile measurements for this
specific change, and new-head hosted integration remain open. Hashing and raw
field slicing remain substantial measured costs; further changes must preserve
numeric token spelling, duplicate detection, byte limits and artifact identity.
The full roadmap and independent external acceptance are not closed by this
consumer optimization.
