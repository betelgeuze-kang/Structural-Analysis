# Full cyclic candidate results in Workbench over actual HTTP

The completed 242-target reinforcement search now has a real HTTP browser
observation using its original result graph, rather than only small fixtures.
The application source is `0a6da4c86`; the only code change is the HTTP browser
test's exact download-byte comparison. Production code and numerical artifacts
are unchanged.

The first adapted observation reached verified desktop/mobile screens but its
Node workers exhausted the 4 GiB heap during large-buffer deep comparison.
The test now checks byte length and `Buffer.equals`, preserving exact byte
identity without constructing a deep matcher representation for each byte.
This addresses verification-tool overhead, not solver or browser acceleration.

## Retained verification

The durable observation passes all four tests in 41.1 s: actual server/browser
loading at 1440 and 390 px, original downloads, tenant isolation/read-only
methods and rejected credentials. The unchanged small fixture also passes all
four tests in 24.3 s. The production build, TypeScript check and viewer-delivery
check pass before these runs. No browser responses are intercepted.

The server registers 75 immutable artifacts / 525,181,454 bytes. All 159
successful responses, totaling 1,181,551,987 bytes across both views and tests,
match original byte lengths and SHA-256 values. Three requests return 401, two
return 404 and one returns 405. The server terminates and records zero new
solver calls and zero fits. Every registered artifact appears in the receipt.

From navigation until the search panel becomes verified, observed times are
16.314 s at desktop width and 16.118 s at mobile width. These single serial
loopback observations include download and validation; they are not a repeated
latency benchmark or production network guarantee. Snapshot import takes
0.462 s; the server records 632,740 KiB peak RSS and 1.273 s process CPU over
37.700 s lifetime. Server RSS is not combined browser-plus-server memory.

Both views verify the same `small` selection and 149.94 synthetic pool minimum,
all eight original solver settings, exact model/result/checkpoint/verification
and search-report downloads, and no horizontal panel overflow. The mobile
capture was visually inspected; the complete review is long and scrollable.
A verified screen does not establish structural adequacy or realistic prices.

## Evidence handling limitation and preserved packet

An intervening default Playwright run cleared repository `test-results` before
the initial failure and first successful adaptation were copied elsewhere.
Those initial raw logs/screenshots/receipts are not retained; the observed
failure and first pass are recorded as historical tool-output summaries only.
The sealed numerical packet was unaffected. The final observation runs in a
separate durable directory, with its original log, receipt, screenshots, adapted
test, exact test patch and audit retained. It is the authoritative browser
observation for this note.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rebar-full-http-kffsdasp`
contains 19 files / 1,392,401 bytes. Reread inventory SHA-256:
`7b57ca1f2e4fccadec18a5c4587d627dc4a3a8abb1b3accc4207512236f79482`.
The source data remain in the separately sealed
[full candidate experiment](rc-rebar-candidate-full-20260913.md).

This supplies an actual large-history Workbench observation and fixes a test
scaling defect. It does not establish learned benefit, independent physics,
production operation, complete repeated user-cost benchmarks or roadmap closure.
