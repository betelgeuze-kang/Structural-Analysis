# Repeated public design comparison on a plastic L frame

Numerical source: `98ce68d128308554bbc98616f0919d19ed2f8daa`. The predeclared campaign executed the actual public design CLI on the existing two-member L-frame geometry, twelve reversing displacement targets and 20 kN constant vertical preload. Four full/pruned pairs used alternating execution order. Public arithmetic was unchanged; the learning experiment's retained twofold profile was not used. Explicit smaller line-search candidates were included without changing acceptance tolerances.

The baseline has four bars at each outer face with 0.000387 m² per bar. Alternatives use 0.00035, 0.00040 and 0.00045 m² at both faces. The common synthetic table declares 100 USD/m³ gross concrete and 2 USD/kg longitudinal steel; screens are 0.1 m translation, 0.02 absolute fiber strain, 0.05 accumulated steel plastic strain and unit concrete-damage bounds. These are internal study inputs, not code-compliant limits or a quote.

## Complete process observation

All eight CLI processes exited zero. Every pair has matching declared inputs, the same verified selection (`cheap`), known work, and identical hashes for retained result artifacts. Repeated result maps are exact within each mode. Full mode analyzes and freshly verifies all four models. Pruned mode analyzes and verifies baseline and cheap, then excludes middle and costly by their strictly higher estimated cost. Their online physical feasibility remains unknown.

| Pair | Execution order | Full process, s | Pruned process, s | Pruned/full |
| --- | --- | ---: | ---: | ---: |
| 0 | Full then pruned | 39.507601 | 20.359567 | 0.515333 |
| 1 | Pruned then full | 39.553003 | 20.520426 | 0.518808 |
| 2 | Full then pruned | 39.899815 | 20.719186 | 0.519280 |
| 3 | Pruned then full | 39.964682 | 20.415176 | 0.510830 |

The ratio of process-time sums is **0.5160566434**, or **48.39% lower enclosing CLI time** in this observation. Totals are 158.925101988 s full and 82.014354689 s pruned. Each process includes interpreter/input handling, analyses, fresh verification and result persistence. Input preparation, parent-side audits, transport and browser review are outside these intervals. This is deterministic cost exclusion, not learned acceleration or measured end-to-end user-time improvement.

Across the four repetitions, full mode uses 32 API invocations / 416 attempted steps / 2,536 Newton iterations and linear solves. Pruned mode uses 16 / 208 / 1,264 respectively. The per-execution API reduction is 8 → 4. There is no unknown numerical work. Each executed model receives its full requested path and fresh verification; four baseline/candidate rows do not mean four independent experimental specimens.

## Quantities and material regime

| Model | Gross concrete, m³ | Longitudinal steel, kg | Synthetic estimate, USD |
| --- | ---: | ---: | ---: |
| Baseline | 0.84 | 85.0626 | 254.1252 |
| Cheap | 0.84 | 76.93 | 237.86 |
| Middle | 0.84 | 87.92 | 259.84 |
| Costly | 0.84 | 98.91 | 281.82 |

The full executions observe accumulated steel plastic strain in every model, ranging from approximately 0.000063805 to 0.000087781. Maximum tensile damage is about 0.99861–0.99872 under the model's concrete law. This expands the earlier cost campaign's observed regime beyond its zero steel plastic strain, while retaining only an internal Euler–Bernoulli/material-law observation. It does not establish independent physical validity, realistic collapse behavior or safety of these designs.

## Original-artifact Workbench review

Repetition 0's pruned originals were packed without numeric regeneration: 22 artifacts, deterministic gzip size 1,710,843 bytes, SHA-256 `508dcee09186aec60289ed8d09588c7a0b46364c42c5b352df2f08bc174253e3`. The retained fixture/test bytes are committed at `a0c49bb67`; three tests passed in 34.6 s on those bytes before commit. TypeScript also passed. The tests verify original-artifact integrity, two-member quantities, observed plasticity, unknown skipped feasibility and byte-exact result downloads, with real 1440 px and 390 px browser views. Mobile rendering was visually inspected. The test file is added to the explicit hosted Workbench suite by `8de403403`.

The browser validates original records and bindings; it does not rerun the solver or promote the separate process timing into a generic product speed claim. The Vite process used for review was stopped after testing.

## Evidence and limits

All 467 frozen numerical source files match both their stored hashes and original Git blobs. The receipt audit checks all original artifact references, the four pairs, repeated result identities, process clocks, selections and work totals, without new solves. Audit source: `8de4034038b6e0a6330609a56f911969909f75b3`.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-l-frame-cost-t3md3b1e`, 732 files / 100,300,442 bytes, excluding interpreter caches and the inventory itself. Inventory SHA-256: `309505899024f5d8d1936962d2fab9bb2ca58daa7e517deb7f878a14e752cefc`. [Complete receipt summary](rc-l-frame-cost-campaign-20260920.summary.json).

This advances repeated nonlinear runtime, canonical changes/quantities/costs and Workbench delivery. It covers one known geometry family on one unpinned host, not independent project generalization, all nonlinear regimes, learned candidate benefit, external verification or release closure.
