# Local fresh-process RC resource observation

Source: `33216141d1f7a2dd577747bc45e8137d590b5aa0`. This follow-up adds CPU, process-local
peak RSS and bounded file-I/O observations around the existing public RC runtime
suite. It does not replace the solver or grant numerical authority to telemetry.
The CLI and exact field scopes are documented in `rc-fiber-design-experiments.md`.

## Verification and failure handling

The final focused process and CI contract run passed **74 tests in 27.09 seconds**.
It includes a real physical suite in a separate worker, caller-directory import
shadowing, policy identity/metadata mutation, invalid inputs, existing-output
preservation, timeout/cancellation cleanup and damaged/detached resource sidecars.
Ruff, compileall and whitespace checks passed. These are focused local checks;
the prepared repository-wide suite and hosted checks remain unfulfilled.

A review probe found that Linux `ru_maxrss` could retain a parent's high-water
history: after a 96 MiB parent allocation, a tiny executed child reported roughly
112 MB through that interface. Linux measurement now uses post-exec
`/proc/self/status` `VmHWM`. A regression verifies the child does not inherit that
allocation. Unreadable/malformed values and other platforms remain unavailable.

Interrupted sidecar writes are retained as raw artifacts. A timeout receives no
complete measurement credit; non-timeout malformed or detached sidecars produce
a blocked manifest with a bounded validation reason. A valid but numerically
blocked suite can retain scoped resource observations without a ready status.
No original or failed output directory is overwritten.

## Fixed-source protocol and physical results

The driver asserted clean status and unchanged HEAD before and after execution.
This session's tests and the reviewer's tests had ended before measurement began;
exclusive ownership of the host is not asserted. The worker was a separate Python
process with PID `186190` and exited successfully.

The predeclared cases use widths 0.401 and 0.402 m in the same local synthetic
serial-cantilever family, two load steps, two measured repetitions, and no warmup.
Each case runs reference, deterministic secant, and frozen learned arms. All
**12 measured runs** passed full-history response and J1-J5 recovery verification;
all **4 reference episode checks** passed. Every run retained positive increment
backend counts and zero backend exceptions. No unsuccessful case was filtered.

The frozen policy is the previously collected study's
`sha256:5f12a3a1efdd26285fd4853e6ea6359b299b2321d626ca1c7abcecbf3a12e892`.
It was not refitted. That policy was trained with four load steps; this resource
probe uses two. Across the four learned runs, the first step's proposal passed
the physical residual guard and was accepted. Each second step reported OOD and
selected reference without attempting the learned seed: **4 accepted learned
steps and 4 OOD reference steps**. Both outcomes retained full physical checks.
These observations are not an independently grouped holdout or a rerun of the
original four-step learning study.

| Width (m) | Arm | Median verified end-to-end (s) | Min-max (s) |
| --- | --- | ---: | --- |
| 0.401 | reference | 9.544684 | 9.463745-9.625623 |
| 0.401 | secant | 9.344664 | 9.343583-9.345745 |
| 0.401 | frozen learned | 9.537011 | 9.493938-9.580084 |
| 0.402 | reference | 9.478234 | 9.466198-9.490271 |
| 0.402 | secant | 9.339237 | 9.335582-9.342892 |
| 0.402 | frozen learned | 9.567020 | 9.485016-9.649023 |

The learned arm was slower than secant in both cases. Two repetitions without
warmup and one synthetic family do not support general acceleration or stable
performance estimates. The report retains dispersion and per-run diagnostics.

## Measured resource scopes

| Observation | Value | Scope |
| --- | ---: | --- |
| Suite CPU | 115.513504 s | All arms, full verification and reference episode checks |
| Suite elapsed | 115.519909 s | Same suite interval |
| Worker cumulative CPU | 116.744241 s | Process start through suite persistence, before resource-sidecar emission |
| Parent-observed worker lifetime | 116.908076 s | Launch through worker exit |
| Post-exec worker peak RSS | 109,953,024 B (104.859375 MiB) | Interpreter/imports, all arms and suite report encoding/persistence |
| Input bytes / read elapsed | 8,991 B / 0.145864 ms | Request, two models and frozen policy; parsing/hashing excluded |
| Suite JSON encoding | 8.718235 ms | Suite serialization |
| Suite write/flush/fsync | 311,985 B / 6.217912 ms | Suite report only |

File API bytes and elapsed time do not establish physical disk traffic or storage
throughput; cached pages are possible. Resource-sidecar/manifest emission I/O is
excluded. The shared-worker peak cannot be attributed to individual strategies.
Policy data generation/training CPU, peak memory and I/O, per-strategy peak
memory, material-only update timing, GPU work and independent hardware validation
remain open. No price, construction saving, release approval or external numerical
validation follows from this observation.

## Retained artifacts

`/tmp/structural-process-observation.2r5b378q/` contains the explicit inputs, frozen
policy, protocol, driver, raw worker suite/resources/manifest, receipt and compact
learned-step review. The raw input/report bytes and source binding were verified
after execution; the original learning study was only read.

- Suite logical report hash: `sha256:0e96103a5332e14e554afbd83be6adc4be3a82d4102b32dc2032d0fdcb173e76`.
- Suite raw-byte hash: `sha256:2654f914df487e7629ad145ae10a684e9ae968a24ba0834adfa033d4cdb60112` (311,985 bytes).
- Manifest raw-byte hash: `sha256:e66b3b83f68961de5aef87e67e9987026b7346681c866101f69f03ede680741b`.

These digests identify local artifacts. They are not signatures or source-code
attestations. Earlier studies retain their original source and resource limits.
