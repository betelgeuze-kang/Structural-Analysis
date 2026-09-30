# Local full learning-study resource observation

Source: `e0b169f5aebcaf0d007046028cc97278e6efb50b`. The fresh-process runner now measures an entire
learning study: physical label generation, train-only fitting and frozen runtime
evaluation. This is local integration and resource evidence for one synthetic RC
family, not independent numerical validation or generalization evidence.

## Implementation and verification

`run_fiber_frame_learning_process` uses the same process lifecycle, raw-byte
binding and failure preservation as the runtime-suite workload, with distinct
learning request/resource/manifest schemas and `study.json`. The original runtime
schema and frozen-policy behavior remain available. An explicit preparation
example writes four canonical models and a request without solving them.

The optional caller-owned `FiberFrameLearningStudyPhaseRecorder` observes three
non-overlapping CPU/wall intervals outside the study/policy/numerical identities.
Default reports retain their existing fields and timing-call behavior. Injected,
invalid, regressing or failing phase clocks cannot alter physical results or hide
solver exceptions; invalid timing is not credited. The recorder is single-use.

- Shared runtime lifecycle, learning-study phases and CI contracts: **95 passed
  in 27.60 seconds**.
- Actual three-case learning-process integration and invalid input workers:
  **7 passed in 98.76 seconds**. Five phase-sidecar mutations reuse the physical
  result and do not invoke additional solves.
- Ready-phase completeness and blocked-prefix regressions: **11 passed in
  1.59 seconds**, without solver execution.
- Changed-source Ruff, compileall and whitespace checks passed.

These are separate focused runs, not a repository-wide suite claim. The shared
runtime test initially exposed a dynamic-import fixture missing `sys.modules`
registration after introducing the profile dataclass; the fixture was corrected
and the final 95-test run passed. Example preparation initially attempted a
no-change baseline edit, which the canonical design API correctly rejects. It now
reuses the baseline and changes only the three authored alternatives.

Review also found that a ready sidecar could mark training/evaluation skipped and
omit their costs. A ready study now requires all three phases completed; after
blocked, exceptional or skipped execution, later phases must remain skipped.
A valid blocked study retains attempted costs and null skipped intervals. Damaged
or detached records cannot receive a ready measurement manifest.

## Fixed-source experiment

The driver asserted clean status and unchanged HEAD before and after execution.
All session/reviewer tests had ended before measurement; exclusive host ownership
is not asserted. The worker generated all labels anew and trained its own policy.
It did not reuse the earlier frozen policy or relabel an earlier observation.

Cases: training widths 0.400/0.390 m, validation 0.401 m, holdout 0.402 m; two load
steps; two measured repetitions; no warmup. These are one synthetic serial-
cantilever family with artificial project/geometry/load-history IDs. Those IDs
exercise declared isolation rules but do not demonstrate independently sourced
projects, geometry families or histories.

All **4 physical collection cases** completed, generating **8 samples**. The
policy's training hash set contains exactly the **4 train samples**; evaluation
labels were generated and charged but were not used to fit the policy. The
validation and holdout cases passed all **12 reference/secant/learned evaluation
runs** and **4 reference episode checks**, including full history and J1-J5
recovery. All eight learned evaluation steps accepted a guarded learned seed;
none reported OOD in this two-step experiment.

Frozen fitted policy hash: `sha256:d02be778faa05028c122c3040e5aa50d1e23013e1d3b3e402bec9f5a4d7bfd35`.

## CPU, elapsed time, memory and file I/O

| Phase | CPU (s) | Elapsed (s) | State |
| --- | ---: | ---: | --- |
| Data collection | 39.118290820 | 39.123174165 | completed |
| Whole training attempt | 0.001121231 | 0.001120793 | completed |
| Frozen evaluation | 117.324330981 | 117.331306075 | completed |
| Whole study workload | 156.449274135 | 156.461137628 | completed |

Collection includes label verification and report conversion. Training includes
the entire fit call, report conversion and frozen policy identity. Evaluation
includes all arms, full verification, reference episode checks, report conversion
and frozen-policy checking. The outer workload additionally includes interphase
setup and final study assembly/hashing. CPU time includes this worker's threads,
not other processes. Most measured CPU cost occurs in collection and evaluation;
training is a small part of this local experiment.

| Other observation | Value | Scope |
| --- | ---: | --- |
| Worker cumulative CPU | 157.684786 s | Interpreter start through study persistence, before sidecar emission |
| Parent-observed worker lifetime | 157.852579 s | Launch through exit |
| Post-exec peak RSS | 111,079,424 B (105.933594 MiB) | Whole worker, all phases, imports and study encoding/persistence |
| Input bytes / read elapsed | 10,384 B / 0.181445 ms | Request and four model files, excluding decode/parse/hash |
| Study JSON encoding | 10.068300 ms | Final study serialization |
| Study write/flush/fsync | 375,490 B / 6.273736 ms | Study output only |

The same address space owns all phases, so per-phase and per-strategy peak memory
remain null. Linux uses post-exec `VmHWM`; unsupported platforms remain unavailable.
File reads may hit cache and do not prove disk traffic or storage throughput.
Resource-sidecar and parent manifest I/O are excluded. This CPU-only workload
makes no GPU measurement claim.

The original study's wall counters retain their earlier scopes. For example, its
training-attempt elapsed value is 0.841705 ms; the new phase interval also includes
report conversion and policy identity capture. Do not sum old counters with these
sidecar values or treat their scope difference as additional solver work.

## Observed comparison and remaining limits

| Case | Arm | Median verified end-to-end (s) | Min-max (s) |
| --- | --- | ---: | --- |
| validation-width | reference | 9.634040 | 9.601803-9.666277 |
| validation-width | secant | 9.502343 | 9.498896-9.505789 |
| validation-width | learned | 9.648825 | 9.631139-9.666511 |
| holdout-width | reference | 9.688081 | 9.652005-9.724157 |
| holdout-width | secant | 9.536579 | 9.530712-9.542446 |
| holdout-width | learned | 9.688611 | 9.687718-9.689504 |

The learned arm was slower than secant in both cases. Neither comparison against
reference nor secant had a positive observed median saving, so all four projected
amortization counts remain unavailable. Two repetitions without warmup are not
stable performance estimates or a general speedup result. The prior four-step
study and frozen-policy probe retain their original source, policy and scopes.

The workflow now observes whole-study CPU, global peak RSS and bounded file I/O
for this local family. Independently grouped licensed corpus evidence, per-phase/
per-strategy peak memory, material-only timing, wider solver/hardware validation,
prepared full-suite/hosted integration and external acceptance remain open. This
observation establishes no construction saving, product readiness or release
approval.

## Retained artifacts

`/tmp/structural-learning-process-observation.1u_zj5sf/` retains explicit inputs,
protocol, driver, raw worker outputs, receipt and this document's extraction code.
Source, input hashes, train sample hashes, physical coverage, phase sums and raw
report/manifest identities were checked after execution.

- Study logical report hash: `sha256:531bac28f009a43893fe42af8f913ee1c0b79462392c27a43d42bb6981d7c3e6`.
- Study raw-byte hash: `sha256:389367fb5c84a38fc417bcc404f2564478b767ab29a6e0fc2cde282ce96d37e3` (375,490 bytes).
- Manifest raw-byte hash: `sha256:2f86621d35c13bd0356a3c110443e190b9e7de360494669e4d20c79615efa1b3`.

These are local artifact identities, not signatures or source-code attestations.
