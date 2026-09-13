# Repeated candidate search: local observation, 2026-09-08

## Source and protocol

The observation ran on clean source `412fda612e442368da0ee3b0add743654d3fdc8d`. The driver
asserted the same HEAD and empty tracked/untracked status before and after the
run. Other agents stopped edits and tests before timing; only bounded read-only
inspection continued. Exclusive host access and independent operator/hardware
acceptance are not asserted. The observation artifacts are preserved under
`/tmp/structural-candidate-suite-observation.1mscbvmx/`, including `run.py`, `base.json`, `protocol.json`, `training.json`,
`suite.json`, `receipt.json` and `execution.log`.

This is two declared candidate pools in one synthetic section family, not an
independent multi-project or geometry/load-history corpus. The baseline is a
3 m cantilever with FY = −1 kN, two integration points and two monotonic load steps.
Four full public collection cases use widths 0.34/0.46 m for train, 0.37 m for
validation and 0.43 m for holdout. Artificial group identifiers do not establish
independent provenance. The policy fits only the two train labels. The terminal
limit rule was declared before collection: the mean of the train terminal labels,
which gave translation `4.551020408163264e-05 m` and absolute fiber strain
`2.991063860793252e-06`. Online/oracle labels do not define these limits.

| Case | Baseline width (m) | Narrow candidate (m) | Near-limit candidate (m) |
| --- | ---: | ---: | ---: |
| pool-a | 0.400 | 0.360 | 0.395 |
| pool-b | 0.405 | 0.380 | 0.399 |

Each case has two measured repetitions and zero warmups. The round-major schedule
is A deterministic→learned, B learned→deterministic, then A learned→deterministic,
B deterministic→learned. Each arm has the same declared pool and budget of two
fresh requests, including its own baseline. Both shortlists are frozen before
online analysis. The full-pool oracle makes three new requests afterward on every
comparison. No baseline, candidate or oracle result is cached between repetitions.
The frozen shortlist/policy/pool binding stayed identical across each case's runs.

## Physical selections and denominators

All four collection cases were ready. All four comparison reports passed their
contracts, and all 16 online plus 12 oracle rows passed full public reference
verification. Requests were training **4**, online **16**, oracle **12**, total
**32**, with no unknown execution counts. The common training artifact was charged
once across both cases and all repetitions.

Both deterministic runs in each case shortlisted `narrow`. That candidate passed
reference verification but failed the terminal screen; both final selections
therefore remained `baseline`. Both learned runs shortlisted and selected the
freshly verified, terminal-feasible `near-limit` candidate.

For each pool there were four candidate observations across its two oracle runs.
The deterministic shortlist missed a feasible candidate twice; the learned
shortlist missed none. Learned false-safe and predicted-safe-unverifiable counts
were zero. These are repeated observations of two candidates per pool, not four
independent physical candidates or evidence of general search accuracy.

The shared synthetic price basis is 100 per gross concrete m³ and 1 per authored
straight longitudinal rebar kg, labelled KRW. In pool A the material estimate
changes from 144.9108 to 144.0108; in pool B it changes from 145.8108 to 144.7308.
These fixture reductions (0.9 and 1.08) are not quotes, detailed takeoffs, labor or
fabrication estimates, or confirmed currency savings.

## Time and cost observations

Per-arm time includes that strategy's shared-preparation charge, policy setup
when applicable, inference, shortlist selection, fresh full reanalysis and final
selection. The same preparation execution is counted once in actual suite time.
Units below are seconds; each row contains only two observations. Population
standard deviation describes these observations, not an uncertainty interval.

| Pool | Strategy | Median | Min–max | Population SD |
| --- | --- | ---: | ---: | ---: |
| pool-a | deterministic | 19.184001 | 19.021097–19.346904 | 0.162903 |
| pool-a | learned | 19.086873 | 19.080917–19.092829 | 0.005956 |
| pool-b | deterministic | 19.024783 | 18.982192–19.067374 | 0.042591 |
| pool-b | learned | 19.095685 | 19.091157–19.100214 | 0.004529 |

Paired deterministic-minus-learned differences for pool A were +0.254075 and
−0.059820 s (median +0.097128 s): the sign changed across repetitions. Pool B's
differences were −0.108965 and −0.032840 s (median −0.070903 s): learned was slower
in both. There is no consistent measured acceleration across the two pools.
No pooled speedup, promotion decision or independent generalization follows.

The report's pool-A arithmetic projection is **397** reuses, obtained from its
positive paired median and the 38.519437 s recorded generation/fit cost. That is a
conditional extrapolation from two variable observations, not an observed or
statistically established break-even. Pool B's projection is unavailable because
its paired median difference is negative.

- Historical label generation including identity/feature preflight: **38.517924 s**.
- Historical fit: **0.001512 s**. Both historical costs are charged once.
- Current suite through aggregation: **267.578781 s**, including **0.007534 s**
  preparation and all online/oracle calls and report-binding checks.
- Accounted generation + fit + suite: **306.098217 s**; excludes final suite report
  encoding/I/O, memory measurement and resource reporting.
- Driver collection/training/suite interval: **306.140277 s wall**, **306.072976 s
  CPU**. It excludes imports, initial protocol writing and final suite file
  encoding/write, but includes intermediate training-file writing and the suite
  result's encoding/copy. It is not a per-strategy CPU observation.
- Dedicated I/O time and peak memory remain unavailable in this suite.

## Artifact bindings and validation

Suite logical report hash: `sha256:c8fadab149c4309e1db7b56f6d8e0fc2412922a393795db9d361690819897f7a`.
Training logical hash:
`sha256:65f47bd2d42c64fcf643b176311c76ddfdd4ba58560a11e1e2bf8bd9b4e8bd60`.
Frozen policy hash:
`sha256:fd547602514b70f0bdd8d3e9ab58d63981452f2cadc32c7a17b834d29f5a06a5`.
Local hashes establish artifact consistency, not signed provenance or external
numerical authority. Raw bytes were rechecked after the driver completed.

| Artifact | Bytes | Raw SHA-256 |
| --- | ---: | --- |
| `protocol.json` | 1,256 | `f76d2c57427e978000e98b0f5cdfdfa31c9c010d8afc35d0332c0bd9a9fba4fe` |
| `training.json` | 31,759 | `7654095ce46654a6a59865131ec4199696bdc677f31f62a595374cbe78d8c605` |
| `suite.json` | 1,533,680 | `80a3bb541e0264ec9626bd2185725353b32c9620b73bf7b65edbdf2522bca44e` |

Focused suite contracts passed **57 tests in 1.86 s**
(`/tmp/structural-m4-suite-tests.log`). Arm-order and training-binding regression
passed **32 tests in 1.69 s**, with 10 unrelated tests deselected
(`/tmp/structural-candidate-arm-order-tests.log`). CI ownership/quality-gate
contracts passed **34 tests in 0.42 s**
(`/tmp/structural-candidate-suite-ci-tests.log`). These are separate groups and
are not presented as a repository-wide suite. Synthetic tests cover execution
order, frozen snapshots, unknown-request failures, blocked timing retention,
historical cost deduplication, report consistency and conditional projection;
they do not provide physical or timing evidence. The actual observation above uses
the default public runner and clock. Ruff and `git diff --check` also passed.

## Remaining scope

The final engineering screen still uses terminal translation/fiber strain. Public
verification of the complete solver path does not turn those terminal measures
into maximum-response envelopes for every committed load step. A later increment
needs step-specific engineering recovery bound to original Newton coordinates and
the validated checkpoint chain; convergence history alone is not that authority.
The current monotonic static profile also does not cover extrema between steps,
cyclic/dynamic histories or design-code/detailing acceptance.

Independent corpus/provenance/licensing, larger and independent geometry/load
families, more repetitions/platforms, per-strategy resources, current-head hosted
integration/review and broader material/3D acceptance remain open. This local
slice does not close the overall roadmap or authorize remote publication.
