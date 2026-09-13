# Public planar full-history backend observation

Implementation source: `e2ce33ad859aecc075ed0ea7a59dffa20a5abbe0`.
The worktree was clean before and after both experiments. Every retained package
file was compared to its committed Git bytes, and the 396-file source inventory
was unchanged. Usage, validation and cost scopes are documented in
`planar-frame-backend-experiments.md`.

Request v2 adds genesis/material memory and every accepted epoch to the existing
terminal SI comparison. Each worker and its parent reassemble the original
checkpoint transitions with the existing engineering recovery implementation;
this extra projection runs no Newton solve. Its costs are measured. Original
public execution, convergence, checkpoint and engineering validations remain
required. V1 requests retain their original behavior and measurement scope.

## Declared protocol and physical outcomes

Preserved directory: `/tmp/structural-planar-history-observation.ZQ5mXz17/`.
`prepare.py`, `protocol.json`, the requests and raw model files were written
before the first measured API entry. `run.py` checks clean Git and package/input
bytes before and after running the two coordinators. No failed slot was retried.

The cases are the existing synthetic RC portal with six free equations, its
five-part member subdivision with 42 free equations, and the small portal with
all nodal reference-load components multiplied by five. The first two models
were copied byte-for-byte from the earlier sealed planar observation. The third
has a new generated model/provenance identity; its load multiplier was fixed
before execution and was not tuned to the outcome. These remain one synthetic
family, not three independent structures or the reserved medium/large corpus.

All use four load targets `[0.25, 0.5, 0.75, 1.0]`, residual tolerance 1e-10,
solver-coordinate increment tolerance 1e-12 and maximum 40 Newton iterations.
Dense, legacy sparse and extended sparse each receive one fresh-worker warmup
and three measured repetitions per case. Backend order rotates, so each measured
backend occupies every position once per case. The timeout is 300 seconds per
worker. Terminal and history comparisons use predeclared absolute/relative 1e-9
tolerances for the five SI groups, with an additional native-unit material-state
group for history. These are regression tolerances, not independent engineering
acceptance criteria.

All **36 declared workers** entered the API, converged, passed their artifact
contracts and retained eligible resources. Nine warmups remain in the report but
are excluded from the measured distributions. The saved histories contain
**144 accepted steps**, plus 36 genesis states. All **24 cross-backend pairs**
(six warmup, 18 measured) match both terminal SI and complete accepted history,
including material memory. Cross-backend checkpoint bytes differ in all 24 pairs;
numerical history parity does not require identical hashes or bytes.

All **18 same-backend repeat comparisons** have identical original result,
validation, checkpoint and history bytes. The small cases have 36 material states
per epoch and the subdivided case 180. Across the first measured histories of
each case/backend, tensile/compressive damage, accumulated plastic strain and
dissipated energy density remain zero at all four accepted epochs. The 5x load
case therefore does not supply yielded, damaged or cyclic material validation.

## Observed costs

Each row summarizes three measured repetitions. Workload includes the public
API and its source-bound validation, explicit public validation, persistence,
and v2 history reassembly/encoding/write. Worker CPU and Linux post-exec `VmHWM`
include the broader fresh-process scope. They are not per-API allocation totals.

| Case | Backend | Workload median s | Min–max s | Population SD s | Worker CPU median s | Worker peak median MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 6 equations | dense | 2.562183 | 2.538785–2.577995 | 0.016107 | 4.263709 | 110.133 |
| 6 equations | legacy sparse | 2.600128 | 2.580312–2.660920 | 0.034296 | 4.317656 | 111.402 |
| 6 equations | extended sparse | 6.762125 | 6.680167–6.771743 | 0.041091 | 8.454453 | 111.516 |
| 42 equations | dense | 10.231643 | 10.229968–10.370054 | 0.065646 | 11.993887 | 117.641 |
| 42 equations | legacy sparse | 10.355438 | 10.332295–10.397744 | 0.027099 | 12.101901 | 119.027 |
| 42 equations | extended sparse | 30.528693 | 30.339442–30.958163 | 0.258860 | 32.255137 | 119.316 |
| 6 equations, 5x load | dense | 2.580365 | 2.551902–2.622382 | 0.028950 | 4.311925 | 110.480 |
| 6 equations, 5x load | legacy sparse | 2.600283 | 2.565754–2.602766 | 0.016892 | 4.305845 | 111.215 |
| 6 equations, 5x load | extended sparse | 6.644957 | 6.633658–6.658523 | 0.010165 | 8.352331 | 111.469 |

Extended sparse is slower in every measured pair: median paired workload ratios
are **2.626748**, **2.983753** and **2.575201**, respectively. Median paired added
times are 4.193748, 20.297050 and 4.064593 seconds. Legacy sparse's paired ratios
are approximately 1.009, 1.012 and 1.009; the latter two cases have sign-changing
paired differences. This does not establish a general improvement.

| Case | Backend | Worker history median s | Parent artifact-validation median s |
| --- | --- | ---: | ---: |
| 6 equations | dense | 0.635791 | 0.782949 |
| 6 equations | legacy sparse | 0.635665 | 0.784177 |
| 6 equations | extended sparse | 0.840158 | 0.986436 |
| 42 equations | dense | 2.320104 | 2.551364 |
| 42 equations | legacy sparse | 2.333053 | 2.500823 |
| 42 equations | extended sparse | 3.278508 | 3.484498 |
| 6 equations, 5x load | dense | 0.639153 | 0.774485 |
| 6 equations, 5x load | legacy sparse | 0.630993 | 0.765355 |
| 6 equations, 5x load | extended sparse | 0.835620 | 0.965775 |

The worker history interval is already inside workload time. Parent validation
includes detached artifact checks and the parent's history reassembly, excluding
launch/wait. Analysis plus history fits inside workload for both wall and CPU;
all broader interval bounds also pass. Do not add nested intervals twice.

The repeated experiment took 426.433706 seconds of wall time and 56.517233 seconds
of parent CPU, excluding child CPU. Its 36 workers consumed 362.786123 seconds
of CPU in total. Worker history projection summed to 48.821932 wall / 48.601753
CPU seconds; parent artifact validation summed to 54.554562 wall / 54.538326 CPU
seconds. Whole driver wall was 438.434244 seconds and parent CPU 57.107854 seconds,
including both experiments and report persistence, excluding pre/post Git checks.

Runtime identities retain Python 3.10.12, NumPy 1.26.4, SciPy 1.12.0, jsonschema
4.26.0 and Linux x86_64 with 24 reported logical CPUs. Parent and workers received
all five declared BLAS/OpenMP thread variables set to `1`. Owned correctness
workers had finished before this measurement. The host was not independently
isolated or qualified; dependencies were observed, not vendored. These v2 costs
must not be treated as equivalent-scope comparisons to the earlier v1 two-step
workloads.

## Retained diagnostic outcomes

Two additional fresh legacy-sparse workers exercised the prior 258-equation model
and the unsupported arc-length request. The first retains `not_converged` with
`sparse_condition_diagnostic_scope_exceeded`, workload 7.076210 seconds. The second
retains `not_run` with `planar_frame_arc_length_experimental`, workload 0.002123
seconds. Both preserve valid diagnostic contracts and resources; neither receives
physical success or full-history credit. Both history intervals are null with
`public_result_not_converged`, and neither produces `history.json`. There are
**38 unique worker PIDs** across the two ordinary experiments. These were API
coordinator calls; no diagnostics CLI exit status is claimed for this observation.

## Regression, audit and retained bytes

Separate focused groups passed: checkpoint-transition recovery **67 (7.49 s)**,
pure history comparison **103 (1.69 s)**, new v2 process contracts **42 (9.94 s)**,
existing v1 process/comparison and recovery neighbors **208 (87.77 s)**, and CI
ownership/quality-gate contracts **40 (0.40 s)**. Ruff/format checks on all ten
changed Python files and `git diff --check` passed before the source commit.
This is focused local verification, not a whole-suite or hosted-CI result.

The new process fixture made exactly two correctness worker requests, dense and
extended sparse with three load steps. Its first positive test passed in 15.23
seconds and is included again in the final 42-test run using retained artifacts.
No subsequent test launched another solver/worker. Cached runs initially had
eight failures from a test `Popen` guard intercepting `platform` metadata lookup,
then one from incorrectly expecting a valid unsupported-execution contract to
fail. The harness and expectation were corrected. Both failed outputs and the
final pass remain in the original accumulated log. The separate transition
fixture's initial expected fiber count was also corrected; no physical gate was
relaxed. The 67/103-test passes are recorded from tool completions; separate raw
logs were not retained. Three original process/neighbor/CI logs and a scope
receipt are copied under `verification/`. The correctness fixture remains at
`/tmp/structural-planar-history-tests-6w9bm15o/experiment` outside this inventory.

A separate saved-artifact audit passed **2,576 checks with zero errors**. It
checked original file/input/source bindings, actual counts, unique PIDs, resource
intervals, checkpoint endpoint/material membership, recomputed both pure pair
comparators and checked all four original files for every repeat. It ran no
Newton solve, reassembly or worker. This is another local integrity review using
the same comparison implementation, not independent structural verification.

Both frozen package manifests have digest
`sha256:4293b5d6a115c1f65731db4ae5724655924f43a3076e136c91ea34b06f828c18`.
The equal before/after source records are 70,720 bytes each, SHA-256
`64bb41021c9f1b1106af02a63d59d2b21761b956f254c6111a9b5026c7eab84f`.
The repeated report is 1,211,571 bytes, SHA-256
`ce3f535687450247130fa7c37e9116cc02ae93b68f3b0af9ad23708ee95a98ee`;
the diagnostic report is 57,468 bytes, SHA-256
`9ac65eef611ec362e0156d243bffba494340a703d3ee32d2c954c65435034a8f`.
`audit.json` is 2,436 bytes, SHA-256
`1bc9b7ce3a982b0d0806d423c941f24c7be828bcafd23691ba5ff09197013c94`.

The sealed directory contains **1,241 files / 47,178,000 bytes**, excluding
`inventory.json`. That inventory is 244,850 bytes, SHA-256
`f4f698e13b3f3f0c861da38ecaac040e553308cec2454ce33f97c847688b2433`.
All entries and the exact file set were rechecked after inventory creation.
Do not modify this retained observation; later runs require a new directory.

## Remaining roadmap scope

This completes the bounded implementation/measurement increment for full-history
cross-backend comparison, not M1/P1 or the roadmap. Broader connected families,
repeated medium/large runs, yielded/damaged/cyclic material histories, licensed
independent corpora and OpenSees/second-solver/operator verification remain.
The measured extended-sparse overhead still needs investigation without weakening
source validation. M2-M5/P2/P3, R1/R2 hosted integration, licensing,
owner/administrator decisions and hardware qualification remain open under their
existing acceptance criteria. No push, PR publication, merge or release occurred.
