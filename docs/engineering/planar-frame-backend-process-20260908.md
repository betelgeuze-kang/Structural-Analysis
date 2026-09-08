# Repeated public planar backend observation

Implementation source: `6f1e7e2c69eb8a52a0ad0d6c7d627e336f651c83`.
The AI worktree was clean when the inputs were prepared and both experiments
started. The reusable runner, comparison semantics and CLI are described in
`planar-frame-backend-experiments.md`. Existing numerical solvers, convergence
tolerances, sparse limits and authority rules were unchanged.

## Frozen protocol and outcomes

Preserved observation directory:
`/tmp/structural-planar-backend-observation-z7lu5syx/`.

`prepare.py` records the model recipe. The first case is the existing synthetic
four-node, three-member RC portal, with six free planar equations. The second
subdivides each member into five: 16 nodes, 15 members, 42 free planar equations.
These are two meshes in one synthetic portal family, not independent structures
or the reserved medium/large corpus. Both use two target factors `[0.5, 1.0]`,
residual tolerance 1e-10, solver-coordinate increment tolerance 1e-12 and at most
40 Newton iterations. No restart is supplied.

The first experiment declares dense, legacy sparse and extended sparse in that
order, one warmup and three measured repetitions for each case/backend. Backend
order rotates by case and repetition. Every measured backend occupies positions
0, 1 and 2 once per case. Each of the **24 slots** has a distinct fresh worker;
all 24 entered the API, converged, passed the artifact contract and retained valid
worker resources. Six warmup rows remain in the raw report and are excluded from
the measured distributions. No analysis from another task was launched alongside
these workers; the host was not independently isolated or qualified.

All **16 paired comparisons** (four warmup, 12 measured) pass the five terminal
SI groups at the declared 1e-9 absolute/relative tolerances. Cross-backend
checkpoint bytes differ in all 16 pairs. Terminal SI parity therefore does not
mean exact cross-backend state-history parity. The **12 same-backend repeat
comparisons** have exact raw result, validation and checkpoint hash/length
identities. Every converged public result also retains its unchanged internal
accepted-history and engineering-recovery verification; the detached comparator
does not numerically replay every checkpoint epoch.

## Scoped resource observations

Values below use the three measured repetitions per case/backend. Workload time
includes the public API's source-bound validation, additional public validation,
rendering and persistence of result/checkpoint/validation files. Worker CPU and
peak RSS cover the broader process scope documented in the sidecar; these columns
must not be added together. Peak is post-exec Linux `VmHWM`, not allocation size
or per-API peak. No injected clocks or runners are used in these observations.

| Case | Backend | Workload median s | Min–max s | Population SD s | Worker CPU median s | Worker peak median MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 6 equations | dense | 1.313346 | 1.301341–1.341736 | 0.016937 | 3.058832 | 109.531 |
| 6 equations | legacy sparse | 1.319139 | 1.306814–1.343809 | 0.015381 | 3.045199 | 110.480 |
| 6 equations | extended sparse | 3.319809 | 3.310995–3.383090 | 0.032111 | 5.046985 | 110.816 |
| 42 equations | dense | 5.017943 | 4.899599–5.062923 | 0.068883 | 6.757780 | 116.004 |
| 42 equations | legacy sparse | 4.921893 | 4.918827–4.938114 | 0.008462 | 6.652661 | 116.988 |
| 42 equations | extended sparse | 14.982313 | 14.858475–15.057937 | 0.082219 | 16.768464 | 117.988 |

In same-repetition comparisons, extended sparse adds a median **1.997649 s** for
the six-equation case and **9.958876 s** for the 42-equation case. Median paired
workload ratios are **2.521038** and **3.000819**, respectively. This is a negative
performance result for these cases, not a reason to bypass CSR validation or
change physical acceptance. Legacy sparse's small paired differences change sign
across repetitions; this sample does not establish a general improvement.

Coordinator experiment wall was 170.813253 s and parent CPU 1.254945 s, through
aggregation and detached verification before final report encoding. Parent CPU
does not include child CPU. Runtime was Python 3.10.12, NumPy 1.26.4, SciPy 1.12.0
and jsonschema 4.26.0 on Linux x86_64, with 24 reported logical CPUs. Each worker
received the five recorded BLAS/OpenMP thread environment variables set to `1`.
Dependency versions and requested settings are observations, not native-library
thread auditing, physical-hardware acceptance or archived dependency binaries.

## Actual failure and unsupported outcomes

A separate two-slot experiment used legacy sparse. The first case subdivides each
portal member into 29, yielding 88 nodes, 87 members and 258 free equations. It
retains `not_converged` with `sparse_condition_diagnostic_scope_exceeded`, no
factorization/fallback credit and workload time **7.048447 s**. The second requests
public arc length on the small portal: it retains `not_run`, the stable
`planar_frame_arc_length_experimental` reason and workload time **0.002161 s**.

Both workers completed the observation protocol, entered the public API and
passed diagnostic artifact validation, while **zero** are counted as physically
converged. Both costs remain available. The diagnostics CLI returned **1** as
expected because neither slot has a converged physical result. This is successful
failure-path retention, not two successful structural solutions.

## Regression and artifact boundaries

Focused regression outcomes were 116 process-contract tests (3.42 s), 59 comparison
tests (1.57 s), 34 CI-boundary/quality-contract tests (0.39 s), and 17 source/workflow/
dependency contracts (0.57 s). Ruff, format and diff checks passed. These are
separate focused runs, not an exact-head full-suite or hosted-CI pass. The final
116-test run reused saved artifacts and launched no additional solver requests.

The process test development made 12 API entries, kept separately from the 26
ordinary observation entries above:

- `/tmp/structural-planar-backend-tests-r0ni0pco/`: four invalid one-step requests;
  the API rejected configuration before producing converged results. The runner
  now rejects declarations outside the existing 2–64-step and 1–200-iteration bounds.
- `/tmp/structural-planar-backend-tests-mse_h0oh/`: four physically converged
  results then rejected by an overly strict namespace import check. The fix binds
  the namespace's exact directory to the frozen schema tree.
- `/tmp/structural-planar-backend-tests-jssxe22b/`: four complete contract/physical
  passes. Later tests reuse these raw artifacts. Synthetic transport, timeout,
  cancellation and mutation tests grant no timing or physical evidence.

Additional regressions reject boolean/integer/float metadata aliasing, wrong
module-name/source-file associations, PID/config/input mixing, rehashed partial
artifacts, contradictory error phases and modified or deleted retained files.
Cancellation retains API entry/exit information; incomplete later slots remain
in the denominator. A missing manifest or checkpoint invalidates affected credit
without discarding the final experiment report.

The two bundles each retain the exact 393-file Python/schema source tree. Their
source manifest digest is
`sha256:223372b356800d4172947b0bca8f8be9a8b6622bd65b3cf005d6beeabd73683d`.
The main report SHA-256 is
`5715ae770709fbe4c9dd2604c42520a8ec078d9d5efedc139daf858947c6ea0c`;
the diagnostics report SHA-256 is
`32a69eb5ac32601142cb98f6e62d198a24024ba035be371e4b679565613a9606`.
Raw exports, per-slot sidecars/logs, the input protocol/recipe, implementation patch,
condensed observation summary and final process-test log are retained. Other
focused test outcomes are recorded as summaries; their original terminal output
was not separately archived. The development test bundles remain at the paths
above and are not copied into the ordinary observation inventory.

The separate artifact/accounting audit passed 2,923 checks, including all 393 Git
blobs, both frozen source copies, 26 worker identities, reported distributions
and raw repeat bytes. It launched no new analyses. `audit.json` is 687,395 bytes,
SHA-256 `3d42acae45b8c5fbd14df2a2acbab8956b7f11ab3d3ab9e04cc6c722d747589d`.
This is a second artifact review, not independent physical verification.

The final sealed directory contains 1,069 files totaling 25,537,270 bytes,
excluding `inventory.json` itself. That inventory is 216,099 bytes, SHA-256
`2f55ef688d68e4e3dc6e1d5faf759d30e363bf01c4d419585115852360d4e1f6`.
Every inventory entry was rechecked after writing it. Do not modify this sealed
observation; subsequent experiments must use a new directory.

## Remaining requirements

The reusable multi-case coordinator is implemented and exercised, but this does
not close P1 or M1 as a whole. Broader connected frame families, repeated medium/
large runs, independently approved tolerance/corpus/licensing decisions and
OpenSees/second-solver verification remain. The reserved fixture-only corpus has
not become an executed corpus through these two portal meshes. The measured CSR
overhead still needs investigation with source validation preserved. P2/P3,
independent M3/M4/M5 acceptance, hosted integration and owner/administrator gates
remain separate requirements. No push, PR publication, merge or release occurred.
