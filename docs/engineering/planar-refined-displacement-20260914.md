# Repeated refined planar displacement-control paths

Two fresh 32-concrete-layer models complete forty prescribed roof-right UX
targets from 2 to 80 mm in 2 mm increments. Their full output files are identical
byte for byte. The terminal proportional load factor is 0.7990589271706917,
not 1.0. This provides a completed bounded alternative control path, not a
repair of the earlier four-target load-control failure or a capacity result.

## Frozen experiment

Source revision: `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`.
The runner verifies every preserved source-file identity and the original
`layers_32` input hash from the section-refinement packet before importing the
frozen package. Both repetitions parse and compile the model afresh. Node N6 is
explicitly checked at (4, 6, 0) m; its native global UX DOF is 15.

The pre-run protocol fixes forty targets and two repetitions. The 80 mm endpoint
extends beyond the earlier approximately 53 mm rejected load-control trial;
it is a numerical exploration boundary, not a requested capacity or design limit.
Existing direct-displacement-control defaults are retained: dense augmented
solution, residual tolerance 1e-10, control and both increment tolerances 1e-12,
maximum 40 iterations, and the original six line-search factors. There are no
retries, target changes, warm-start fits or public API/default modifications.

The entire original force vector remains proportional to the solved factor,
including vertical loads. This is not a constant-axial-load test. The material
history and intermediate targets differ from load control; the paths are not
claimed equivalent for accuracy, work or runtime comparisons.

## Executed observations

| Observation | Repetition 0 | Repetition 1 |
| --- | ---: | ---: |
| Committed targets | 40 / 40 | 40 / 40 |
| Convergence-history rows | 223 | 223 |
| Line-search attempts | 183 | 183 |
| Core path time | 91.767011 s | 92.038820 s |
| Compile time | 0.493385 s | 0.474980 s |

Both statuses are ready and contracts pass. The auditor checks every parent-to-
accepted checkpoint transition and each step's residual, control, increment,
coordinate and solver binding gates. Final accepted checkpoint identity is
preserved, and the two complete paths compare exactly. Each full path file has
SHA-256 `6d685a2e3d7e2b56bf21714705c2e543e94088c9da6c9e209e337cf34f81de65`.

Selected accepted displacements and load factors:

| Roof-right UX | Proportional load factor |
| --- | ---: |
| 2 mm | 0.141153630 |
| 12 mm | 0.504963243 |
| 22 mm | 0.652275525 |
| 42 mm | 0.750430478 |
| 62 mm | 0.786988590 |
| 80 mm | 0.799058927 |

The sampled load factor increases throughout; no descending branch was observed.
At 80 mm the relative equilibrium residual is 8.5330309e-12, control error is
zero, final free increment is 1.3009842e-13 m, and load-factor increment is
9.3528944e-13. These pass the unchanged gates. They neither show equilibrium at
factor 1 nor establish an ultimate load or physical validity.

Total experiment time was 196.454322 s, including fresh compilation and output
serialization/hashing inside the experiment interval. Core paths account for
183.805831 s, compilation 0.968365 s, leaving 11.680127 s of other in-interval
work. Source verification before that interval and the separate auditor are not
included, so this is not complete user-flow latency. Each full result occupies
201,735,353 bytes. Two exact repetitions establish bounded reproducibility, not
a statistical speed comparison or learned net benefit.

## Evidence and next boundary

The packet retains the pre-run protocol, runner, auditor, both complete paths,
run summary and audit. The runner creates a fresh output directory and writes
its location to `/tmp/structural-refined-displacement-root.txt`; the auditor uses
that pointer to verify path hashes, complete equality and accepted-state chains.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-refined-displacement-61gurys3`

Seven payload files, 403,495,119 bytes; inventory SHA-256:
`304016d55852bd3f7bec1d39033210e9d6da40ec1a97bfda6f02ffebe90f2a05`.
Machine-readable observations: `planar-refined-displacement-20260914.summary.json`.

The earlier 32-to-64 layer agreement was measured only on a different accepted
load-control prefix. It does not establish discretization convergence for this
80 mm material history. That remains to be measured before this longer path is
used as a numerical reference for learning or performance comparisons. External
physics verification, licensing, learned benefit and full roadmap closure remain
separate requirements.
