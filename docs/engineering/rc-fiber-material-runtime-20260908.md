# RC fiber material trial runtime observation — 2026-09-08

The optional material recorder observed the declared Newton/terminal/guard scope
without changing any selected numerical step hash from the previous fixed-input
observation. All 12 measured runs and four reference episode checks passed.
This is local resource evidence for one synthetic serial-cantilever family.

## Source and protocol

- Fixed clean source: `be8e5eef04c94ec92ca14d07939fca2c3a0e8fd7`. The driver asserted the same
  HEAD and a clean worktree before and after execution.
- Inputs: the exact request, two model files and frozen policy bytes from
  `/tmp/structural-process-observation.2r5b378q/`; no refitting or regeneration.
- Widths 0.401 and 0.402 m; two load steps; reference/secant/opt-in learned arms;
  two repetitions each; zero warmups. The old policy was trained on four steps.
- Frozen policy: `sha256:5f12a3a1efdd26285fd4853e6ea6359b299b2321d626ca1c7abcecbf3a12e892`.
- Outputs and reproduction driver: `/tmp/structural-material-process-observation.ohl66hsa/` (`run.py`, `protocol.json`,
  `receipt.json`, `result/suite.json`, `result/resources.json`, `result/manifest.json`).
- Both agents finished tests before measurement. The process audit found no
  competing Python/test/git process before launch; this does not establish an
  exclusive host or independent hardware acceptance.

## Exact measured scope

`MaterialTrialRuntimeRecorder` surrounds each explicitly observed steel or
concrete `integrate` API call. Counts include actual calls that raise; rejected
inputs before a call do not count as an executed trial. It excludes section
accumulation, element/frame assembly work, checkpoint validation and compilation/
full J1-J5 verification replays. API intervals include timing overhead and material
API work such as validation; they are not isolated constitutive-equation kernels.
No instrumentation-overhead correction or cross-source overhead experiment was run.

Newton, terminal and physical guard material records are summed once across all
attempts, including unsuccessful seeded attempts when present. Material time is
already inside inclusive assembly time; it must not be added again or subtracted
twice. Unsupported custom sections keep their original integration behavior and
mark coverage incomplete. Observed subsets remain available while complete totals
and distributions become unavailable. Separate sidecars preserve numerical and
checkpoint identities; `guard_material_trial` does not extend the guard receipt.

## Observations

Counts below sum both repetitions; times are the median of the two complete runs.
Inclusive assembly is attempted Newton + terminal + physical guard assembly.
End-to-end also includes full path/recovery comparison and is a different scope.

| Width case | Strategy | Material API calls | Material median ms | Inclusive assembly median ms | Verified end-to-end median s |
| --- | --- | ---: | ---: | ---: | ---: |
| width_0_401 | Reference | 160 | 0.944094 | 24.805666 | 9.539239 |
| width_0_401 | Secant | 160 | 0.927703 | 24.454386 | 9.383324 |
| width_0_401 | Frozen learned | 192 | 1.117525 | 29.213578 | 9.538811 |
| width_0_402 | Reference | 160 | 0.918309 | 24.278678 | 9.647726 |
| width_0_402 | Secant | 160 | 0.929821 | 24.323784 | 9.421312 |
| width_0_402 | Frozen learned | 192 | 1.119088 | 29.442369 | 9.572484 |

All measured material rows had complete declared-scope coverage, zero material
exceptions and zero timing errors. The full measured scope made
**1,024 API calls in 11.913080 ms**:
512 concrete calls
(8.933083 ms) and
512 steel calls
(2.979997 ms). Guard material time was
1.499114 ms and is included in that total.
Material intervals accounted for 3.8056%
of the 313.036921 ms inclusive assembly total for this declared scope.
This percentage does not describe all material work during full verification.

All selected-step hashes matched the prior frozen-policy observation exactly.
The learned arm used 4 guard-accepted seeds and 4 OOD reference steps.
It remained slower than secant in both cases. No default promotion or generalized
speedup is supported.

Whole workload CPU was 116.072326597 s and
wall time was 116.132099086 s. Worker CPU through report
persistence was 117.361489099 s, with post-exec Linux
peak RSS 111,853,568 bytes
(106.671875 MiB). Input reads covered
8,991 bytes in 0.130614 ms;
report encoding took 16.976943 ms and
write/flush/fsync of 556,500 bytes took
6.502313 ms. The report grew because
it retains per-attempt/guard coverage and aggregate timing. These file API timings
exclude resource/manifest writes and do not measure physical disk traffic.

## Verification and bindings

Separate focused groups passed; they overlap and are not summed:

- 22 material trial tests (1.61 s): cyclic exact response/parent bytes, unsupported
  and mixed coverage, custom overrides, failed calls and invalid clocks.
- 52 existing section/beam/runtime-suite/learning-study tests (22.86 s).
- 75 stateful/runtime/CI tests (109.94 s): existing actual reference/secant/learned
  and failed-seed runs reused for accounting, full recovery, missing metadata,
  invalid scope/subtotals/types and CI ownership.
- 8 final instrumentation-failure tests (1.63 s), including a reproduced nested
  clock failure: an outer `finally` replaced the material exception. Runtime now
  checks recorder errors before accepting either failed or normal solver returns,
  so that defect cannot be treated as recoverable physical nonconvergence.
- Ruff and `git diff --check` passed before the fixed source commit. The actual
  process observation above ran after that final exception-handling repair.

The driver rechecked report/resource raw byte lengths and SHA-256 digests,
input digests, source stability, full physical verification and per-run material
subtotals against inclusive assembly. SHA-256 here binds local artifacts; it is
not a signature or independent verification receipt.

- Suite logical report hash: `sha256:f4c3241978db7e8d441c62d5f5b6a86f593495e5d7522b404800ea0a1ac63948`.
- Suite raw byte hash: `sha256:9f29d19b0eb54ed6f9fe468287b520d0d7eb73da657fd3b8eb08924a7f369e91`.
- Manifest raw byte hash: `sha256:c788d9313e48461f0c597c64ccb5a34f64c34af05197082695cfb22c8042caf1`.

Per-phase/per-strategy peak memory, all-replay constitutive timing, independent
project/geometry/load-history corpora and hardware/operator/cross-code acceptance
remain open. This slice does not close material/3D public promotion, licensing,
repository administration or hosted exact-head/full-suite integration.
