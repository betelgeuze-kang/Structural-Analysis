# Incremental timing observation with order-balanced control paths

Frozen numerical source: `2b9a1405427781052c39be63fba9eb5dcf13a84a`.
The archived source, exact model, experiment script and original outputs are
retained together. This uses the authored small L-frame in binary64 and the
existing three-target reversed control request, with and without its declared
constant preload. Secant supplies the proposal; there is no learned policy.

Both conditions record assembly counts. One also enables the new assembly
timer. Each preload configuration has two repetitions, first untimed/timed,
then timed/untimed. Every benchmark executes reference, secant, proposal and
fresh reference, for 32 full paths and 112 numerical step records overall.
Every paired original step byte sequence, phase count and full-history
comparison is identical. All fresh references are exact and execution work
is complete. This is observational implementation evidence, not independent
physical validation or an independent-case generalization test.

| Constant preload | Pairwise timed/untimed whole-benchmark ratios | Untimed median seconds | Timed median seconds |
| --- | --- | --- | --- |
| Absent | 0.9960189, 1.0030871 | 1.1834075 | 1.1828628 |
| Present | 1.0023635, 0.9742737 | 1.6085337 | 1.5894940 |

The enclosing intervals include the complete benchmark call and serialization;
they exclude packet inventory creation. Phase intervals keep the narrower
dispatch/status scope of the built-in recorder. The study interval is
11.159818156 seconds and overlaps the table intervals; do not add them.
The two repetitions per configuration do not resolve instrumentation overhead
against runtime variability. Values below one are not timer-induced speedup
evidence. This comparison also does not measure the cost of count recording
relative to a completely uninstrumented benchmark.

The packet contains 1,614 files totaling 89,233,794 bytes, including frozen
source and interpreter cache files. Every listed file was independently
reread and checked against its recorded length and SHA-256 after execution.
The packet and external inventory are read-only:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-timing-overhead-tl47t0aw`.
Inventory SHA-256:
`bc68503f49ff5e71fc25f10e8a788552b7dabe617720ccf7329059515d41f976`.

Timing remains opt-in. No reward, tolerance, default solver strategy or
acceptance gate is changed. Larger nonlinear regimes, independent physical
references, learned net benefit and release acceptance remain open.
