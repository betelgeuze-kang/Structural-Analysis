# Repeated process costs of strict RC cost exclusions

Source `8ae676acb1efb25bdbb983ae043f35289bdf9ce4` ran a predeclared five-case
campaign through actual design CLI subprocesses. All 20 processes completed;
each case ran full then pruned, followed by pruned then full. The script and all
inputs were stored before the first numerical execution. No learned policy was
used. These cases reuse the earlier internal reinforcement-study family and are
not independent project or geometry holdouts.

Observed host: AMD Ryzen 9 5900X, Linux 6.5.0-26 x86_64, Python 3.10.12.
CPU frequency and background workload were not pinned; this limits timing
generalization.

The four ordinary cases vary width (0.32/0.48 m) and a reversing target history
(small: -1/-2/+1 mm; large: -4/-8/+4 mm), each with a 600 kN constant axial load.
Three alternatives vary top/bottom reinforcement area around a fixed baseline.
Each execution declares four models. Prices and limits are synthetic, common
within a case and fixed before execution. The fifth case uses a predeclared very
small strain limit so no candidate can provide feasible pruning authority.

## Observations

Times below sum the two complete CLI processes per mode, including interpreter
startup, input reads, numerical analyses, fresh verification and result storage.
Parent preparation/audit, transfer and browser review are outside these intervals.
Nested numerical times are not added again. Ratios are per-case ratios of sums;
individual paired ratios remain in the JSON record. No cross-case aggregate is
reported because the unsuccessful-selection case remains in the denominator.

| Case | Full process sum, s | Pruned process sum, s | Pruned/full | API calls per execution |
| --- | ---: | ---: | ---: | --- |
| w32-small | 6.037599 | 4.403152 | 0.729289 | 8 → 4 |
| w32-large | 6.320846 | 4.640072 | 0.734090 | 8 → 4 |
| w48-small | 5.904401 | 4.392347 | 0.743911 | 8 → 4 |
| w48-large | 6.319414 | 4.612163 | 0.729840 | 8 → 4 |
| no-feasible-screen | 5.945152 | 5.906382 | unavailable | 8 → 8 |

In the four ordinary cases, both modes select `cheap`; pruned mode omits `middle`
and `costly` only after prior verified feasible authority. Full mode analyzes and
freshly verifies all four models. Every retained result hash equals its full-mode
counterpart, and repeated result maps are exact within both modes. Skipped models
retain unknown physical feasibility online; the full run is separate evidence.

The large cases reach maximum concrete tensile damage 0.794586 and 0.843503 among
computed candidates, respectively. Steel accumulated plastic strain stays zero.
This observation therefore includes concrete-damaging paths but does not cover
steel plasticity, arbitrary histories, or all nonlinear regimes.

The ordinary cases show **25.6–27.1% lower enclosing process time** in this small
local observation. This is deterministic cost exclusion, not an AI speedup.
Two order-balanced repetitions do not establish statistical robustness or
production-wide performance. Both modes analyze all models in the no-feasible
case, select none and receive no qualified speed ratio; raw clocks are retained.

## Reproduction and preserved evidence

Run with a new output directory on the stated source:

```sh
PYTHONPATH=.:src python3 scripts/run_rc_cost_pruning_campaign.py --output /absolute/new/path
```

Packet (not overwritten):
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-cost-pruning-k4yedxy4/study`.
All 662 inventory entries were separately checked for exact SHA-256 and length.
Inventory SHA-256:
`33225a1daf91cdd068ad273c9b62cb8f5458c2275d1bcacd4f1c3c62836f3edc`.
Protocol SHA-256:
`a5b2ab6e8a13a8c136043b6b578843540d2d3b42fc857aca021d3353580b6a8c`.
Campaign parent interval including audits: 54.520114 s, excluding final inventory
creation. The committed [summary](rc-cost-pruning-process-campaign-20260920.summary.json)
retains raw per-case clocks, pairs, counters, selections and material-state maxima.

Focused tests: 7 passed in 7.25 s, including actual full/pruned solves and ratio
eligibility refusal for changed inputs, unknown work, unmatched results, missing
selection and incomplete status. Ruff and diff checks passed. The optional
production behavior remains unchanged by this measurement script.

This advances the repeated-runtime evidence and verified candidate-selection
workstreams. It does not establish learned benefit, independent physical accuracy,
external data admission, full CI completion, design approval or release readiness.

## Subsequent failure-accounting hardening

A later reader/driver review found that an original-byte audit could succeed on
an incomplete JSON object, after which pair summarization raised and interrupted
the remaining experiment. The driver now uses strict JSON, retains pair-level
schema/audit errors and process clocks, and continues planned pairs with a null
ratio. Missing reports, nonzero exits, malformed clocks, duplicate candidate rows,
erased invocation records and differing execution inputs cannot receive speed
credit. Terminal success also requires the declared case/pair denominator.

The focused suite now has 10 passing tests (7.33 s), including an injected campaign
where every subprocess fails: all planned pairs and attempted costs remain in the
final summary/inventory and the driver exits nonzero. This injection is software
failure-path evidence, not a numerical runtime observation. All 10 original pairs
were re-read with the tightened checks; the eight eligible ratios are unchanged.
The original packet, driver copy, clocks and inventory were not modified.
