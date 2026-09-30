# Local isolated-strategy resource observation

The additional `fiber_frame_strategy_process_suite` experiment gives each strategy
its own fresh Python worker for every declared case, warmup and repetition. It
reuses the existing solver, guarded proposal and full selected-path verification
logic. A learned worker decodes one frozen policy and reuses that instance; it
does not collect training data, fit a policy or reset it between runs.

## Implementation and verification

Each worker persists its complete canonical checkpoints and trial assemblies.
The parent validates the input byte bindings, compiled problem/coordinate/config/
load-history bindings, ordered execution coverage and raw report/resource hashes.
It then compares every measured history with the reference using the existing
numerical comparison rules. Checkpoint ancestry must match the immediately prior
state. Local self-validation alone does not grant cross-worker comparison credit.

CPU/wall intervals distinguish compilation, warmup execution, measured execution
and full verification, reference-only baseline episode checks, and parent
comparison. Inclusive verified runs also include snapshot preparation. Nested
phase and material intervals must fit their enclosing intervals; unavailable
material metadata remains unavailable. Parent comparison is a subset of parent
orchestration CPU. Missing workers retain their expected rows and null complete
totals; valid resource observations of physically blocked workers retain attempted
costs. Independent worker peaks cannot be added or subtracted.

The reference worker's RSS includes its extra baseline episode checks. This
prevents a claim of equal-scope peak-memory advantage. RSS includes imports,
input processing and strategy-report persistence, using post-exec Linux `VmHWM`;
it is unavailable on platforms without a validated process-local measurement.
Input/report file I/O is the explicit bounded read/write scope, excluding
resource-sidecar, parent-manifest and combined-report persistence. Reads may use
cache and are not measurements of physical disk traffic. No GPU work is measured.

The legacy in-process comparator now passes detached canonical snapshots through
the same comparison implementation. Its comparison interval therefore includes
serialization and snapshot validation at this source version; old timing records
retain their original scopes. Numerical algorithms and tolerances are unchanged.

Focused verification before the fixed-source observation:

- Existing process/learning regressions: **59 passed in 123.61 seconds**.
- Existing actual two-step runtime cases: **2 passed in 69.35 seconds**.
- Final strategy contracts and CI ownership contracts: **107 passed in 2.20
  seconds**, including 73 strategy cases and 34 CI cases.
- The new process integration collected three physical label cases (six samples),
  fitted once, and ran one validation case with one warmup and one measured run
  in each of three fresh workers. All workers and the parent comparison passed.
  Its first test invocation had 42 passes and one test-only tuple/list equality
  failure. Normalizing that assertion and rereading the preserved artifacts
  produced 50 passing tests without additional fitting or numerical solves.
- Final transport, cost-subset, unavailable-metadata and typed ancestry negative
  tests: **60 passed in 2.41 seconds**, reusing those same artifacts with no new
  solver paths or training calls. Ruff and whitespace checks passed.

These are separate correctness runs with overlapping coverage, not performance
observations or a repository-wide test result. The process fixture artifacts are
retained under `/tmp/structural-strategy-process-nwxb6ywv/`. Later cost/ancestry
negative tests reuse those completed reports and rebind all outer hashes so they
exercise the inner contract rather than merely detecting changed bytes.

## Fixed-source experiment

Source: `8161e6c7ea5aac319cbf896bbfecb43a84d5cf01`. The driver asserted clean
status and the same HEAD before and after execution. All session tests and agent
edits had stopped before measurement; exclusive host ownership is not asserted.
Original request/model bytes were unchanged. The additional experiment ran through
the public suite CLI with exit 0 and three distinct fresh worker PIDs.

First, a new full learning-study worker collected widths 0.400/0.390 m for train,
0.401 m for validation and 0.402 m for holdout. Four cases produced eight samples;
only the four train samples fitted the policy. All cases use two load steps and
the unchanged public solver tolerances. Each evaluation case/strategy has one
warmup and two measured repetitions. These are one synthetic cantilever family
with artificial split IDs, not independently sourced projects or histories.

The study completed **18 strategy paths: 6 warmup and 12 measured**, plus four
reference episode checks. Its policy was extracted unchanged and used for an
**additional 18 paths: 6 warmup and 12 measured**, plus four reference episode
checks in three separate workers. The additional workers did not collect labels
or fit a policy. Thus the workflow has four label cases, one training attempt,
36 strategy paths and eight reference episode checks in their distinct scopes.
These are top-level execution categories; the full-verification/replay work inside
them is included in measured costs rather than counted as new top-level requests.

Both experiments passed all 12 measured histories. Post-run read-only comparison
also found exact matches for all 12 paired path, terminal checkpoint, checkpoint
chain, terminal receipt, numerical result and engineering result hashes between
the study and additional experiment. All declared warmups completed. Frozen policy
hash: `sha256:6b67e5a2c77322e55865c910274206bc5a16282fe503c2bab0065ef62771860f`.

## CPU, elapsed time and memory

The full learning-study sidecar keeps all upfront and earlier evaluation costs:

| Learning-study interval | CPU (s) | Elapsed (s) |
| --- | ---: | ---: |
| Label collection and conversion | 38.819186240 | 38.821510917 |
| Whole training attempt and policy conversion | 0.001113680 | 0.001113266 |
| Earlier evaluation, all strategies and verification | 117.071539049 | 117.079946719 |
| Whole learning-study workload | 155.901063553 | 155.911801303 |

Its cumulative worker CPU was 157.173539276 s and whole-worker peak RSS was
113,422,336 bytes (108.167969 MiB). The three phase intervals are subsets of the
workload; they are not added to the outer cost. This earlier evaluation cost is
retained even though the policy is subsequently evaluated in separate workers.

The additional experiment observes the following independent process scopes:

| Strategy | Workload CPU (s) | Cumulative worker CPU (s) | Launch-to-exit (s) | Peak RSS (bytes / MiB) |
| --- | ---: | ---: | ---: | ---: |
| Reference | 40.772959411 | 42.020064755 | 42.212671192 | 111,403,008 / 106.242188 |
| Deterministic secant | 38.555827713 | 39.829753387 | 40.010906313 | 110,292,992 / 105.183594 |
| Frozen learned | 39.108968755 | 40.347150883 | 40.559752796 | 111,292,416 / 106.136719 |

Reference-only episode checks consumed 1.900215694 CPU seconds and 1.900342239
elapsed seconds inside that worker. Its peak contains these checks and cannot
be adjusted by subtracting a separately observed peak. Each strategy's measured
run CPU sum, including full authority verification and snapshot preparation, was
38.784486298 / 38.466943213 / 38.994452894 s, respectively. Warmup CPU was
0.072225512 / 0.072879972 / 0.097601223 s; compilation and report work remain
accounted in the enclosing worker scopes.

The additional workers used 122.196969025 cumulative CPU seconds in total.
Parent orchestration used 0.602345562 CPU seconds, of which 0.203059658 s belonged
to the 12 full-history comparisons. Add parent CPU only once; comparison CPU is
not an additional cost on top of it. Parent elapsed time was 123.396502242 s.
Its interval ends before combined-report encoding/persistence. The outer driver,
resource-sidecar emission and remaining coordinator I/O are outside these observed
CPU scopes; this is not a complete host-CPU bill. Combined peak memory remains
unavailable. The strategy report leaves historical training cost null; the bound
learning-study artifact above supplies its distinct measured cost without
altering the strategy report or retraining the policy.

## Bounded file I/O

| Worker | Input bytes | Read (ms) | Report bytes | Encode (ms) | Write/flush/fsync (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full learning study | 10,384 | 0.165115 | 632,353 | 18.786362 | 6.669410 |
| Reference strategy | 5,206 | 0.099024 | 591,028 | 12.502450 | 6.921296 |
| Secant strategy | 5,211 | 0.098853 | 592,903 | 12.722981 | 6.595359 |
| Learned strategy | 8,797 | 0.130565 | 596,164 | 12.787977 | 6.639597 |

Each strategy reads its own request and the two model files; the learned worker
also reads the frozen policy. Input reads exclude decoding/parsing/hashing.
Report write values exclude the resource sidecars, manifests and combined report.
No disk throughput or cache-independent I/O claim follows from these numbers.

## Observed repeated comparison

Each interval below includes execution, complete selected-path verification,
snapshot preparation and parent cross-worker comparison. It excludes compilation,
warmups, the separate reference episode checks and process startup/report I/O.

| Case | Strategy | Median elapsed (s) | Min-max (s) | Median CPU (s) |
| --- | --- | ---: | ---: | ---: |
| validation-width | reference | 9.659599 | 9.623668-9.695530 | 9.658981 |
| validation-width | secant | 9.591077 | 9.488925-9.693230 | 9.590530 |
| validation-width | learned | 9.713824 | 9.681217-9.746431 | 9.713266 |
| holdout-width | reference | 9.771657 | 9.748923-9.794391 | 9.767139 |
| holdout-width | secant | 9.681606 | 9.572878-9.790334 | 9.676748 |
| holdout-width | learned | 9.837972 | 9.812638-9.863306 | 9.817807 |

The learned arm was slower than secant by 0.122746 s and 0.156366 s in the
respective medians. All eight measured learned steps accepted guarded seeds,
with no baseline recovery. Material instrumentation was complete in its declared
attempted Newton/terminal/guard scope: 1,088 calls, 12.676024 ms, zero material
exceptions and zero timing errors. This is a subset of inclusive assembly time;
it excludes compilation/checkpoint/full-verification replays and warmups.

Two repetitions and one worker per strategy in fixed reference/secant/learned
launch order do not demonstrate stable performance or remove ordering effects.
The comparison provides no positive learned acceleration or demonstrated
amortization. Raw reports retain dispersion and all execution rows.

## Retained artifacts

`/tmp/structural-strategy-resource-observation-8161e6c7e/` retains original and frozen
inputs, protocol, driver, extraction/verification scripts, both experiments,
source/coverage receipt and post-verification result. Raw report identities:

- Learning study: `sha256:45120e37babec476739d14cee71135596520df2164fb1f65a7fdd6ed8788e63a`
  (632,353 bytes); logical report hash
  `sha256:fe18289f342e56902c7a2d215cfa12270954546e71792bc5c52c37cb9bdcae9a`.
- Frozen policy file: `sha256:35808be2189e340fe29c1f532d64d2d0dcfeb061752e9c29fbda556495fe50c3`
  (3,501 bytes); policy identity is the separate canonical artifact hash above.
- Combined strategy report:
  `sha256:d22f25e187608e4f65d9ad1bd24c51955ae7443321e247a4faef4559f905e32d`
  (2,498,758 bytes); logical report hash
  `sha256:eac13924099bb03a049e5ec245adcfa2b5b79d1e56ba25480ec7d773d1c88a13`.
- Strategy experiment identity:
  `sha256:dfd51f478d62439cda287b0832fee91269ebf25782029526583b0109b7b261c9`.

The receipt binds all individual worker reports, resources, manifests and inputs.
Post-verification reread all recorded artifacts, confirmed unchanged bytes and
matched paired physical identities without any additional numerical solve.

## Evidence limits

Source revisions and hashes establish explicit identities, not attestations.
This implementation does not supply independently grouped licensed training
data, independent solver/hardware validation, generalized acceleration, confirmed
construction savings, hosted full-suite acceptance or release approval. The
broader roadmap and the original dirty checkout remain separate.
