# Secant-correction learning: same-source local observation

Observed 2026-09-08 at clean committed source
`508d45b34e9dc8ac06f18e87dd70ababfd352f86`. The opt-in v3 policy and full
learning/frozen-file workflows passed the declared synthetic cases. V3 did not
reduce Newton iterations or verified end-to-end cost relative to deterministic
secant. It does not justify changing the default or closing M3 net performance.
The [usage and contracts](rc-fiber-secant-correction-warm-start.md) describe the
new target, strict artifact binding and unchanged v1/v2 defaults.

## Fixed protocol and complete execution denominator

Original artifacts are retained in
`/tmp/structural-secant-correction-observation.Cx6vE4/`. `protocol.md`, `prepare.py`,
`run.py`, both study requests, all models and a saved-policy request template were
written before execution. The preparation copied all 394 tracked package files,
checked them against Git blobs, and saved hashes. Every worker imported that same
frozen package. Source and prepared input bytes were checked around each execution;
the final source snapshot matched, and the implementation checkout was clean at
the same commit before and after measurement. These checks are local consistency
evidence, not source/operator/hardware attestation.

The fixture is `tests/fixtures/fiber_frame_candidate_process/base.json`: a serial
RC cantilever with two integration points and two concrete layers. Only length,
width, FY reference load and case metadata vary. The recipes reproduce the prior
conditioned study and were not selected using these new outcomes:

| Split | Length (m) | Width (m) | FY (kN) |
| --- | ---: | ---: | ---: |
| Train | 3 | .400 | -.8 |
| Train | 3 | .460 | -1.2 |
| Train | 4 | .400 | -1.2 |
| Train | 4 | .460 | -.8 |
| Validation interior | 3.25 | .415 | -1 |
| Known holdout-load-OOD diagnostic | 3.75 | .440 | -2 |

Artificial project/geometry/load-history labels remain within one synthetic family.
The OOD diagnostic was already known; neither independent provenance nor blind
prediction is established. All cases use load factors .5 and 1, residual tolerance
1e-10, increment tolerance 1e-12 and 40 maximum iterations. Ridge 1e-6, OOD margin
.1, two repetitions, zero warmups, default guards/damping and response tolerances
(absolute 1e-10, relative 1e-8) were fixed before either study.

Three fresh workers executed sequentially: v2 control, v3 correction, then saved
v3 policy. Each whole study collected six complete cases and 12 accepted samples,
fitted only the eight original train rows, and evaluated two cases across three
strategies and two repetitions. All **24 evaluated paths** passed full-history
response comparison and J1–J5 recovery; all **eight separate reference episode
checks** passed. The later saved-policy worker loaded the reported v3 artifact
without fitting and passed **two additional selected paths** through full J1–J5
recovery. It did not execute a separate reference comparison or reference episode.
There were no failed or retried measurement workers and no post-outcome tuning.

## Behavior and comparison limits

Both learned policies made four in-range proposals across the validation repeats;
all passed the physical guard with damping 1. V3 accepted relative residuals were
approximately .15305745 and .15303803 at its two steps. Deterministic secant's
second-step residual was approximately 1.22e-15. Both learned policies still used
four total Newton iterations per two-step path, versus secant's three. The changed
target therefore did not improve the initial guess enough to save an iteration.

Both studies detected all four learned OOD steps and used the reference parent
start. No seeded attempt ran for OOD. No failed-seed rollback/recovery occurred in
these measurements; injected failure tests remain separate. All measured paths
reported zero dissipated energy, so yielded/cyclic behavior is not demonstrated.

Within each study, checkpoint byte parity with reference was reported for four
reference runs and two learned OOD runs. The four secant and two in-range learned
runs passed response/history tolerances but did not have exact checkpoint bytes.
Complete original checkpoint byte chains are not exported by the study report;
saved report hashes and audits cannot independently replay those original chains.
The saved-policy report includes comparison snapshots and authority bindings, but
does not add independent physics validation.

## Verified time and dispersion

Seconds below include strategy execution and full-path verification. Each row has
two repeats. Attempted solver time is a smaller nested scope in milliseconds.

| Policy study | Case | Strategy | Min (s) | Median (s) | Max (s) | Solver median (ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| v2 | Validation | Reference | 4.041205 | 4.062941 | 4.084677 | 27.625199 |
| v2 | Validation | Secant | 3.996009 | 4.058076 | 4.120143 | 22.919929 |
| v2 | Validation | Learned | 4.045149 | 4.057889 | 4.070629 | 27.987601 |
| v2 | OOD | Reference | 4.039133 | 4.051304 | 4.063474 | 27.655270 |
| v2 | OOD | Secant | 3.983409 | 4.007290 | 4.031171 | 22.937890 |
| v2 | OOD | Learned | 4.060378 | 4.064062 | 4.067747 | 27.700531 |
| v3 | Validation | Reference | 4.102837 | 4.119308 | 4.135779 | 27.878597 |
| v3 | Validation | Secant | 4.114040 | 4.137175 | 4.160311 | 23.830059 |
| v3 | Validation | Learned | 4.137936 | 4.198289 | 4.258641 | 28.276861 |
| v3 | OOD | Reference | 4.115252 | 4.197784 | 4.280317 | 28.060524 |
| v3 | OOD | Secant | 4.040953 | 4.054923 | 4.068893 | 22.966841 |
| v3 | OOD | Learned | 4.112262 | 4.117197 | 4.122132 | 27.841272 |

V3 learned-minus-secant median differences were **+61.113376 ms** for validation
and **+62.274551 ms** for OOD. Paired repetition differences were respectively
**+98.330791/+23.895961 ms** and **+43.369593/+81.179508 ms**. All four pairs were
slower; both v3 secant amortization rows have no positive saving and null reuse
projection. V3 inference totaled 3.133123 ms in range and 2.825883 ms for OOD,
including model feature preparation. Learned guard time totaled 20.677971 ms
(eight assemblies) and .006470 ms (zero assemblies), respectively. These are
already included in strategy times; full verification remains the dominant cost.

Small apparent gains in other rows must not be hidden or promoted. V2 validation
had a .1876165 ms median advantage over secant, while its paired differences were
-49.514773/+49.139540 ms. V3 OOD had an 80.587331 ms median advantage over reference,
with paired differences -168.055043/+6.880382 ms, despite executing the same
reference start with extra inference. The generated local projections (v2: 4,848
reference or 130,544 secant reuses; v3 OOD: 311 reference reuses) are arithmetic
extrapolations, not observed break-even or robust acceleration. Fixed study order,
two repeats and shared host scheduling limit causal interpretation. The earlier
50987f7 study also predates recovery-cost changes and is not a current-source
timing baseline.

## Full learning and process costs

| Scope | v2 seconds | v3 seconds |
| --- | ---: | ---: |
| Data generation, including evaluation labels | 24.488356962 | 25.027988089 |
| Internal trainer | .003697441 | .006350789 |
| Training attempt | .003705111 | .008592793 |
| Evaluation | 50.533356742 | 51.606125278 |
| Study interval | 75.031264188 | 76.643372701 |
| Driver API wall, including launch/wait and manifest | 76.815524691 | 78.413528930 |
| Driver API parent-only CPU | .019758605 | .016831308 |
| Worker process CPU through report persistence | 76.649540891 | 78.247215957 |

V3's training attempt includes report conversion, strict decoding and frozen-policy
checks; its evaluation includes report conversion and final policy-byte checks.
Legacy internal v2 intervals preserve their original smaller scopes. The common
phase recorder includes conversion/frozen checks for both: training wall/CPU was
.004465116/.004465482 s for v2 and .008595733/.008595934 s for v3. Collection phase
wall/CPU was 24.488962212/24.487675566 and 25.028555347/25.027113625 s; evaluation
phase wall/CPU was 50.537739297/50.535177483 and 51.606130118/51.602984185 s.
The upfront amortization charges were 24.492062073 and 25.036580882 s. Nested
intervals must not be added; offline evaluation is separately disclosed.

| Whole worker | Peak RSS (bytes) | Input bytes read | Report bytes written |
| --- | ---: | ---: | ---: |
| v2 study | 115593216 | 15381 | 675993 |
| v3 study | 114556928 | 15425 | 676259 |
| Frozen v3 learned-only | 111915008 | 12722 | 299648 |

Learning phases and strategies share each study's address space; their individual
peak RSS is unavailable. The saved-policy worker is a separate learned-only batch,
not a per-phase subtraction from a study. Its workload wall was 8.255518617 s,
worker CPU 9.837289643 s, and driver API wall/parent CPU
10.018422688/.039421138 s. The read/write counts are bounded file-API scopes,
not physical disk traffic; sidecar/manifest I/O is excluded. GPU time is unavailable.

Environment: Python 3.10.12, NumPy 1.26.4, SciPy 1.12.0, jsonschema 4.26.0,
Linux x86_64 and 24 logical CPUs. OMP/OpenBLAS/MKL/VECLIB/NUMEXPR thread environment
values were requested as 1; native thread behavior and hardware exclusivity were
not attested. Owned tests and solvers stopped during the sequential measurements.

## Verification and retained records

Focused verification passed 64 policy algebra/identity tests, 66 new process
contracts, 122 existing learning contracts, 68 runtime/process neighbors and 44 CI
boundary/quality-gate contracts. Four real-process tests in the existing groups
were deselected; the three committed-source workers above exercised the actual
new paths separately. These 364 tests are not 364 independent physical cases.
Changed Python files passed Ruff/format checks and the diff passed whitespace
checks. One initial new process-test expectation was corrected to accept the
existing unknown-schema fail-closed KeyError as well as ValueError; this did not
relax production decoding. No full-suite or hosted pass is claimed.

Original file logs are retained for the 64-, 68- and 44-test groups. The 66- and
122-test outcomes are recorded from their tool completion outputs; no original
file log is retained for those two groups. `verification-receipts.json` discloses
that distinction and does not reconstruct raw logs.

The v3 policy identity is
`sha256:316138124d7be56be2c683e260808d1af1d8b9acb9722ba51baec0e3cfd9b958`.
The original v2/v3 sample contents and policy train membership can be compared
directly. Selected raw SHA-256 bindings are:

| Relative path | Bytes | Raw SHA-256 |
| --- | ---: | --- |
| `v2/study.json` | 675993 | `08d29d0297f59e43a8fcee8c6a369c9d90a96a97b4889d485b4aac5b1c324496` |
| `v3/study.json` | 676259 | `9f2dc23a81e2e8c783e4d0af03cbbea352f975309052af20cf015690a5ed1e81` |
| `frozen/strategy.json` | 299648 | `3062649b985ce55840119090f9fd58e87990ab8a70aaecfefa7dbf68db2a28d1` |
| `inputs/v3-policy.json` | 7628 | `e4cba69ea7c78674fc06542602b6bfaa093d9bf48676369cbf6a7d3023cd7894` |
| `source-before.json` and `source-after.json` (each) | 75290 | `d76dcad2c1d14e4eacf2cb30773d04e9c05d67723df14cd24a4f2e9b521d058f` |

The retained directory contains the source snapshots, implementation patch,
requests/models/policy, raw study/strategy/resource/manifests, worker stdout/stderr,
driver receipts, extraction script/summary and focused verification logs. The
artifact audit passed 905 checks, including 394 source files against Git/current
bytes, identical original v2/v3 samples, train membership, declared denominators,
three distinct worker PIDs, raw resource bindings and basic nested cost arithmetic.
Both saved-policy paths have the same path/terminal-checkpoint/authority bindings
as their original v3 study runs. This audit executed no fitter or solver. A separate
local document review also found no numerical or scope mismatch.

`artifact-inventory.json` seals **446 files / 10,115,808 bytes**, excluding itself.
The 85,942-byte inventory has raw SHA-256
`0eb6e76848afc55aa68d091716280fe3c304f08257708fb2c4c94c5a79e2d977`.
Every listed hash/length and the complete file list were reread after creation;
the sealed observation is not modified thereafter. Original train membership,
numerical bindings and failure denominators remain inspectable without additional
solver calls. All independent corpus/provenance/licensing, yielded and
cyclic coverage, generalization, net performance, hosted integration and human
approval requirements remain open across the full roadmap.
