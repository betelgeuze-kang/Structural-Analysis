# RC control candidate ranking and full-reference selection

The direct displacement-control path now has a candidate learner and search CLI.
Source `ef1f81f95ec8d343aaa012464fede2ca1195a89a` binds the entire control
request, constants, topology/material context and canonical section changes.
Three full-path training models and four disjoint evaluation models exercise the
actual CLI. Both online arms and the later exhaustive oracle select `cheap`;
this single authored-family observation establishes no learned advantage.

## Implemented path

`rc_control_candidate_cli train` produces full-reference-verified labels,
train-only preprocessing and a serialized SVD ridge policy. Every label includes
its own fresh replay and accepted constant preload. Verified rows failing the
caller screens remain labels. The seven targets cover terminal and full-history
translation/strain plus steel plastic strain and concrete damage.

`rc_control_candidate_cli search` freezes both complete rankings and shortlists
before the first online solve. Price order uses a common declared price table;
learned order ranks predicted passing candidates, abstentions, then predicted
failures, with price/ID ties. Predictions never authorize selection. Each arm
executes the existing complete RC design comparison and fresh verification on
its own baseline and shortlisted alternatives. The optional exhaustive oracle
runs after both online arms and is charged separately. Historical training is
charged once outside the online totals. Missing or unknown numerical work stops
execution before another arm.

The bounded interface accepts one to sixteen valid canonical alternatives,
rejects duplicate physical models and overlap with training models, and rejects
changed direct-control/fixed model contexts before execution. It does not yet
transfer across independent projects, geometry families or load histories.
Preflight-invalid alternatives currently reject this search as a whole; this is
not the invalid-row-retaining behavior of the underlying design comparator.

## Actual CLI observation

The 3 m cantilever uses training widths 0.32, 0.40 and 0.54 m, and evaluation
baseline 0.43 m with alternatives 0.36, 0.46 and 0.50 m. Seven prescribed targets
`[-.002, -.004, -.002, 0, .002, .004, 0]` m include two reversals; every full path
also includes its own -600 kN constant-load preload. The standard public direct
API arithmetic and terminal polishing are used, without the separate retained
arithmetic benchmark override. Screen limits of 1 are permissive development
inputs. Prices of 100 per cubic metre and 1 per kilogram, denominated KRW,
are synthetic arithmetic, not supplier quotes.

| Phase | Models including baseline | Core calls including fresh replay | Newton / linear | Internal wall seconds |
| --- | ---: | ---: | ---: | ---: |
| Training labels and fit | 3 | 48 | 128 / 128 | 2.754322 |
| Price-order arm | 2 | 32 | 88 / 88 | 1.805651 |
| Learned-order arm | 2 | 32 | 88 / 88 | 1.782859 |
| Later exhaustive oracle | 4 | 64 | 164 / 164 | 3.589344 |

The complete numerical observation has 176 core calls and 468 Newton/linear
iterations. All three alternatives receive non-abstained, predicted passing
scores, so both frozen orders are identical. The selected synthetic estimate
is 137.7108 for `cheap` in all three comparisons. Equal online work and a tiny
single-run timing difference do not establish a learned speedup.

The search clock including preflight, ranking, both arms, optional oracle and
I/O is 7.190283 s; ranking takes 0.002967 s. The training fit takes 0.001099 s
within its training total. Parent clocks including interpreter startup are
4.505268 s for training and 8.907320 s for search, with child CPU 4.504536 s and
8.901770 s. Peak child RSS is a cumulative 114980 KiB observation, not isolated
per-phase memory. These are shared-host timings with no repetition/dispersion
or hardware qualification. Final report writing is outside internal clocks.

## Original-record and existing Workbench verification

The audit checks 438 frozen source files, policy/sample/report hashes, disjoint
physical identities, original full-path artifact byte references and all work
counters. Ridge stationarity is independently recounted without refitting;
relative residual is 3.15565e-16. All four design comparisons contain verified
full paths, including preload, across eleven total rows. Audit time is 0.019994 s,
with no new Newton calls or fits.

The unchanged, frozen Workbench TypeScript design validator accepts all four
comparison reports and their model/result/checkpoint/verification/quantity/price
bindings. Its 88 artifact reads cover 4,104,400 bytes and take 0.780990 s under
Node 20.19.0 and TypeScript 5.0.2. This is a data-consumer check, not a browser,
HTTP/authentication, rendering or pinned frontend delivery qualification.
The combined direct-control search review panel remains to be implemented;
individual arm reports already use the existing RC design comparison format.

The original CLI implementation passes 39 selected Python tests including
existing RC design regressions. Two earlier test-fixture failures used forbidden
zero limits; the positive-limit guard was preserved and fixtures corrected.
Ruff and scoped mypy pass. Original logs are retained.

## Explicit candidate coverage and prediction mistakes

Follow-up source `9bad3dd2e14b6948500e480fb8731c1155a98dbf` emits search v2 with
an explicit candidate coverage audit. It records missed feasible alternatives,
predicted-pass/verified-fail errors, predicted-pass/unverifiable cases and
predicted-fail/verified-pass errors, with IDs and counts. Baselines are excluded
from this denominator. A missing oracle produces null counts; the price-order
strategy's prediction counts are not applicable. Incomplete verification or a
partial requested-screen set remains unknown, never a verified physical failure.

All 45 selected Python tests pass, including genuine small generated studies,
injected optimistic predictions that fail full-path screens, missing/aliased
oracle rows, missing work and abstained/unverifiable distinctions. Ruff and
scoped mypy pass. Controlled predictions test authority, not learned accuracy.

A separate observation applies the committed coverage function to the original
sealed CLI records after checking all 573 files. Both arms leave `middle` and
`costly` unrequested even though the later oracle verifies their requested
limits: two missed feasible alternatives per arm. Neither is cheaper than the
selected `cheap`; missing feasible alternatives does not mean missing the
minimum estimate. Learned false-safe and false-negative counts are zero in this
permissive three-alternative development pool. The deterministic prediction
counts remain null. This separate recount takes 0.030319 s with no new solves or
fits; the original v1 numerical packet is unchanged and not relabeled as a v2 run.

## Preserved packets and remaining acceptance

The numerical packet is sealed at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-control-candidate-9llgy6n9`, with 573 files / 13,186,109 bytes and
inventory SHA-256 `36f6e82817ff8cc232269f4f5c4b7f5e5bc3838a5c381f4764fe632c49a6d7e8`.
The later coverage packet is sealed separately at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-candidate-coverage-zxs9m0at`.
The [machine summary](rc-control-candidate-selection-20260910.summary.json)
retains both inventories, original costs, process outcomes and coverage counts.
All observed numerical, consumer and audit processes are terminal.

M4 still requires the combined Workbench review, broader candidate pools and
repeated independent-family evaluation with full training/online/oracle costs.
The oracle uses the same reference solver and provides no independent physical
validation. External-data admission, actual quotes, hosted acceptance and the
full roadmap remain open. The separate [warm-start selection](rc-runtime-selection-20260910.md)
now has its completed original audit and continues to select deterministic secant.
