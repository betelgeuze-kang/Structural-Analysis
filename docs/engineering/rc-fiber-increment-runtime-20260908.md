# Local vector increment cost observation

The runtime roadmap previously reported linear increment time and call counts as
unmeasured. The optional `VectorIncrementRuntimeRecorder` now wraps the existing
vector backend call and retains its elapsed time, calls and exceptions in the
caller-owned timing sidecar. It never enters numerical results or checkpoints.
Newton's remaining unattributed time excludes both assembly and increment time,
so those phases do not overlap in its total.

The measured scope includes matrix conversion and sparse factorization/diagnostic
work. It is not isolated BLAS/LAPACK time. An uninstrumented solve keeps the same
calculation path and numerical payload; a reaction-only solve invokes no clock or
increment backend. Singular and unexpected failing backend calls are counted.
Invalid clocks raise instrumentation errors, rather than being reported as
physical nonconvergence. Caller-injected clocks remain ineligible as timing
evidence under the existing benchmark contract.

## Verification

- Stateful solver, Newton configuration and runtime benchmark: 66 passed in
  108.49 seconds, including dense/sparse exact numerical equality, singular
  backend counting, zero-equation behavior, exception recovery and invalid clocks.
- Connected planar sparse integration, result/recovery binding, sparse diagnostics,
  runtime suite and learning study: 86 passed in 240.43 seconds.
- CI ownership/quality contracts: 33 passed in 0.35 seconds.
- Changed-source Ruff, compileall and whitespace checks passed.

These runs are not summed or presented as a repository-wide full-suite pass.
Prepared exact-head hosted checks remain required.

## Fixed-source physical observation

Source: `dd9950ebc66f2bf25c66ffb2b83fee5665b29253`. HEAD and clean status were
asserted before and after execution. The session's other verification processes
had completed before the measurement began. This does not establish exclusive
host ownership or independent-platform validation.

The predeclared protocol used `public_rc_fiber_frame_cantilever.json`, widths
0.400 and 0.395 m, two load steps, two measured repetitions and no warmup. Each
case used fresh reference Newton and deterministic secant arms. Both cases are
the same synthetic serial-cantilever family. No learned policy was evaluated and
no price or construction-saving claim applies.

All 8 measured runs passed full history and J1-J5 recovery; all 4 reference
episode checks passed. Each run recorded positive backend timing and call counts,
zero backend exceptions, and exact accounting of Newton total as assembly plus
increment plus remaining time. Numeric correctness, not a timing threshold, was
the acceptance criterion.

| Width (m) | Arm | Median backend time (ms) | Min-max backend time (ms) | Median verified end-to-end (s) |
| --- | --- | ---: | --- | ---: |
| 0.400 | reference | 0.063283 | 0.049211-0.077355 | 9.5940 |
| 0.400 | secant | 0.036736 | 0.036641-0.036831 | 9.4225 |
| 0.395 | reference | 0.048992 | 0.048591-0.049392 | 9.6182 |
| 0.395 | secant | 0.036421 | 0.036371-0.036470 | 9.4577 |

The increment backend is a small fraction of verified end-to-end time here.
Two repetitions without warmup do not support a stable performance estimate or
general speedup claim. CPU process time, peak memory and I/O are still unmeasured
by the in-process benchmark; this change does not complete all cost accounting.
Earlier learned-policy studies retain their original source and measurements.

The protocol, complete report, driver and receipt are retained locally under
`/tmp/structural-increment-observation.4yyrox/`. The suite report hash is
`sha256:41804ba52c0b16f78874ba172d9fe2d8f052c604f168ce1f559ff945e869c43e`.
It identifies this local report, not a signature or independent approval.
