# Timed reuse on the declared retained-arithmetic yielded prefix

Frozen source: `9f711a6a3` (full revision in the execution receipt).
The existing yielded-prefix command used retained arithmetic, native immediate
line-search reuse, two order-balanced repetitions and optional assembly timing.
The authored geometry, all 16 targets and original response tolerances remain
unchanged. This is a separate arithmetic configuration, not a replacement of
the failed binary64 study documented in `rc-yielded-reuse-timing-gate-20260914.md`.

All four benchmarks complete: baseline/reuse, then reuse/baseline. Each runs
reference, secant, the identical secant proposal and fresh reference. The
16 complete paths produce 256 numerical step records. All full-history
comparisons pass, all fresh references are exact, and baseline/reuse step
bytes match exactly. The proposals are deterministic; no learned policy is
fitted or evaluated.

| Repetition | Order | Baseline whole benchmark, seconds | Reuse, seconds | Reuse / baseline |
| --- | --- | --- | --- | --- |
| 0 | baseline, reuse | 26.339734527 | 20.873148109 | 0.792458561 |
| 1 | reuse, baseline | 26.150771385 | 20.876761179 | 0.798322958 |

Each benchmark's original dispatch count falls from 788 to 578 with 210
recorded reuse hits. Only primary-iteration dispatches change: 274 to 64.
Line-search dispatches stay at 322, terminal refinement at 128 and final
observation at 64. Primary-assembly time falls from 6.826/6.787 seconds to
1.571/1.574 seconds. Final observations and terminal refinement remain fresh.
Observed enclosing savings are 20.75% and 20.17% in this small repeated study;
these are not general speedup claims, a timer-overhead estimate, or learned
net benefit. No default strategy is changed.

The enclosing times include benchmark verification, serialization and enabled
instrumentation. The entire subprocess execution takes 96.118664634 seconds;
the subsequent raw-output audit takes 0.050250928 seconds before inventory
creation. Nested phase and benchmark intervals must not be added. The audit
recounts every step's actual dispatches and reuse hits, checks original step
bytes, and reconstructs phase durations from invocation records against the
benchmark summaries. This is software/numerical consistency evidence, not
independent physical validation or a complete user-interface cost measurement.

Read-only source/output packet (2,441 files, 135,991,733 bytes):
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-yielded-retained-timing-jzpknyz5`.
External inventory SHA-256:
`f50c8f49f3dfcf627def523e88c9098a9740ff9f660ca57cf5adce78fe439223`.
The auditor and exact output are separately retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-retained-timing-auditor-a3my25iz`;
inventory SHA-256:
`f5fdff19defbab004d777c08db6613b687eef0c8d2d9f1b93ad2eb94b625de72`.

The failed binary64 observation and its null paired cost remain valid. This
result supports further profiling of this retained-arithmetic configuration,
not promotion of unrelated models, larger structural systems or release gates.
