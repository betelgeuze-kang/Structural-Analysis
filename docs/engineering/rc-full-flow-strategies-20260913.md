# Matched RC analysis-to-review flows — 2026-09-13

Source `561a1483af6045cb4e4ce0b9e62fd8495905b6ed`. Four fresh standalone strategy executions
were followed immediately by the same automated Workbench review through real HTTP.
This observes a broader runtime interval than the earlier separate CLI/process and
cohort-review measurements. It remains one known structural family, not independent
generalization or physical qualification.

## Fixed scope and protocol

Before execution, the driver froze the Python package source from the exact commit,
verified five existing model/request/experiment/policy/training inputs against their
sealed inventory, and fixed four slots at budget 11: price then learned, followed by
learned then price. Each CLI runs in a fresh process with single-thread BLAS settings
and the existing immediate line-search assembly reuse. No fit or new label generation
was requested. The original learned policy is reused.

For each slot, the enclosing clock starts before analysis-process launch and ends
after its separate review process exits. Review includes HTTP server startup and
snapshot validation, browser launch, verified standalone search display, selected
candidate `w047`, four byte-exact downloads (model, result, checkpoint, verification),
server/browser teardown and response-byte checks. Parent report reading and process
bookkeeping between the two subprocesses remain inside the enclosing interval.

The observer uses real loopback HTTP without browser request interception. Both
strategies receive identical viewport and download tasks. The transport helper now
accepts `--study-directory` only with an explicit `--expected-report-hash`; cohort
and study directory flags are mutually exclusive. Four existing actual-HTTP tests
passed using this pinned directory route. A preflight review of a prior original
study passed before launching fresh analyses. Those tests/preflight, source/input
preparation, production build, separate audits and human think time are outside
the measured per-slot interval. This is not first-install or human workflow latency.

## Measured results

| Slot | Analysis process (s) | Review process (s) | Enclosing flow (s) |
| --- | ---: | ---: | ---: |
| b11-o0-price_order | 11.328861 | 3.294344 | 14.623332 |
| b11-o0-learned_order | 11.064206 | 3.306671 | 14.371035 |
| b11-o1-learned_order | 11.123289 | 3.249923 | 14.373377 |
| b11-o1-price_order | 10.999815 | 3.248283 | 14.248227 |

Price flow total: **28.871558883 s**. Learned flow total: **28.744411524 s**.
Online learned/price ratio: **0.9955961034346896**. Historical training is counted
once at **2.761753795 s**, giving learned-plus-historical/price
**1.0912526561754619** (about 9.1% more recorded time).

These are sums of four measured flow intervals, not an inferred sum of overlapping
CLI/server/browser timers. Historical training is a reused earlier observation,
not a new fit performed on this host during the campaign. The overall campaign
parent clock also includes receipt writing and between-slot checks and is retained
separately in `process-outcome.json`.

All four executions selected `w047` with fresh full-reference verification. Budget
11 evaluates the same complete candidate pool in both strategies, so the roughly
0.44% online difference is not evidence of learned search acceleration. Two orders
on one family are insufficient to characterize timing variance or unseen designs.
The training-inclusive result does not establish net savings.

The runs produced 44 model result rows / 88 full paths including fresh verification,
704 core calls and 1,760 Newton iterations/linear solves. Review checked 428 exact
HTTP responses and 16 exact downloads; all browser error lists were empty, analysis
and review processes returned zero, and servers closed. A separate accounting audit
checked slot order, source/input bindings, interval containment, selection quality,
response bytes and work counts without rerunning numerical paths.

## Evidence and remaining scope

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-full-flow-strategy-q1_jdt6p` contains 1129 files / 29,808,111 bytes, bound by
sibling inventory SHA-256 `22019da5549eed8cf5ea950c6159948767178043b2d3494571d0c191441b9e7f`. It preserves the fixed
protocol, frozen package source, original inputs, new complete graphs, per-slot
stdout/stderr and review receipts, asset hashes, driver and audit. Previous sealed
packets remain unchanged.

This closes the absence of a matched automated analysis-to-review timing observation
for this case. It does not close unseen project/geometry/history evaluation, learned
net benefit, full hosted CI, independent physical/model validation, licensing,
owner/administrator or hardware dependencies. Workbench's process-cost section
still shows its declared analysis-process scope; this broader flow observation is
a separate supplemental report, not silently substituted into that display.
