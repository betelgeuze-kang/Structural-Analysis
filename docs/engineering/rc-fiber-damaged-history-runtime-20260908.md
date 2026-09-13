# Damaged RC history and frozen-policy runtime observation

At clean source `d1f9ff9af0a4f894dca3527f1fcc4003e3caa8ec`, the new
[constitutive-history inspector](rc-fiber-constitutive-history.md) recovered
retained concrete tensile damage from a complete public RC L-frame load path.
The predeclared higher-load case did not converge. All 18 repeated strategy
paths remain in the report: nine full-history passes and nine blocked paths.
The whole suite remains blocked; the successful case supports a separate local
comparison. This extends the earlier elastic observations without establishing
steel yielding, cyclic behavior, independent physical validation or roadmap closure.

## Implementation and fixed protocol

The companion binds the original typed public result, model/configuration,
checkpoint bytes and complete engineering history after the existing source
validation. It reports native material values and parent-state changes at genesis
and each accepted epoch. Its explicit source validator rejects a rehashed report
whose statistics, identities, types or claims differ from the source-derived
report. The original solver, convergence gates, public result and policy defaults
are unchanged. Detached or incomplete public results cannot supply a complete
companion. Inspecting or explicitly validating a companion charges the existing
source recovery; the statistics do not require an additional public analysis.

The measurement root is `/tmp/structural-rc-material-observation.b4YnWkcu/`.
Preparation exported 397 tracked package Python/schema files from the commit,
compared their bytes with Git and the clean worktree, and froze all four inputs.
The driver checked the same source, HEAD, clean status and inputs before and after
the public inspections and runtime worker. Source-before and source-after agree.
These are local consistency checks, not a signed operator/source attestation.

Both synthetic models use the existing noncollinear serial L-frame geometry
`(0,0) -> (2,0) -> (2,1.5)` m, a fixed first endpoint and downward tip FY.
Each member has three integration points and a 0.4 x 0.6 m RC section with
0.05 m cover, twelve concrete layers and two aggregate reinforcing layers
(four bars per layer, 3.87e-4 m² per bar). The public compiler's rotation scale
remains 2 m. The material parameters are the existing local recipe, without
independent experimental calibration.

| Case | Reference FY | Declared proportional steps | Actual accepted steps |
| --- | ---: | ---: | ---: |
| L150 | -150 kN | 4 | 4, through factor 1.0 |
| L300 | -300 kN | 8 | 5, through factor .625; attempted .75 failed |

Residual tolerance 1e-10, increment tolerance 1e-12 and maximum iterations 40
were fixed. Two standalone public analyses each attempted the new companion.
Then one fresh worker evaluated both cases using reference Newton,
deterministic secant and opt-in AI, three measured repetitions each, zero
warmups and a 1,200-second timeout. Strategy order rotates so each arm occupies
each position once per case. No measurement request was retried or tuned after
its outcome. These known cases were selected following the feasibility probes
below; they are not blind or independent holdouts.

The AI input is the exact saved v3 single-member low-load policy from
`/tmp/structural-secant-correction-observation.Cx6vE4/inputs/v3-policy.json`.
Its logical identity is
`sha256:316138124d7be56be2c683e260808d1af1d8b9acb9722ba51baec0e3cfd9b958`.
There was no fitting or new training-label collection in this frozen-policy
workload. Historical generation/training costs remain in the
[earlier observation](rc-fiber-secant-correction-runtime-20260908.md), outside
these timings; no amortization or net learned benefit is claimed.

## Actual retained material history

L150 has 84 modeled material points per epoch: 72 concrete and 12 aggregate
steel states. These are member/integration/fiber points, not a count of bars.
The following values come from the source-verified companion. Energy is the
original engineering recovery's cumulative MJ value, not a sum of densities
or a sum across epochs.

| Epoch | Load factor | Positive tensile-damage points | Increased from parent | Maximum tensile damage | Cumulative dissipation (MJ) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Genesis | 0 | 0 | unavailable | 0 | unavailable |
| 1 | .25 | 0 | 0 | 0 | 0 |
| 2 | .50 | 3 | 3 | .5004110442616231 | .0000034256890283357385 |
| 3 | .75 | 9 | 9 | .868235733480065 | .000039786795694006846 |
| 4 | 1.0 | 17 | 17 | .9699183857765405 | .00012222922495455125 |

Positive and increased counts happen to coincide for this ramp. The API keeps
them separate, and the pure tests also cover retained history and signed
reversal. Steel accumulated plastic strain and concrete compressive damage stay
zero in the saved accepted states. This demonstrates modeled tensile-damage
activity; it does not demonstrate committed steel yielding or validate the
material model against a physical experiment.

L300 retained an exact rollback and five accepted epochs, but its partial result
was rejected by the companion. The failure at load factor .75 does not establish
structural capacity or collapse. It supplies no complete engineering history or
full-path physical success.

## Repeated strategy outcomes

L150 passed all nine full J1–J5/history paths and all three separate reference
SolverEpisode checks. Secant used 19 Newton iterations per path versus 22 for
reference and AI. Its nine available seeds passed the physical guard: damping
was 1, .5 and .5 in each repeat, requiring 24 guard assemblies in total. No
failed-seed recovery occurred for L150. Secant checkpoint bytes differed from
reference, while complete response/material histories passed the original
elementwise tolerances (absolute 1e-10, relative 1e-8).

The frozen AI policy reported OOD at all 30 attempted steps: 12 in L150 and 18
in L300. Every OOD step selected the reference parent start, with zero AI seeded
attempts and zero AI physical-guard assemblies. L150 reference and AI terminal
and chain hashes match the separately saved public checkpoint. This observes
fallback on an unfamiliar layout; it does not establish useful learned proposals
in damaged material states. Runtime reports preserve authority/comparison hashes,
but do not export every strategy's original checkpoint byte chain for independent
replay. The standalone public checkpoints are retained separately.

L300 blocked in all nine paths. Secant's sixth-step seed passed its initial
residual guard but failed during Newton; all three repeats recorded exact
rollback and a failed baseline recovery. Selected Newton counts were 29 and
attempted counts 31, versus 34/34 for reference and AI. The extra failed work
remains charged. The three L300 reference-episode entries report verification
unavailable, so the complete denominator is **3/6 episode passes**. A false
full-history flag here means incomplete verification; it is not itself proof of
a response mismatch between two complete solutions.

## Time and resource scopes

L150 values below are seconds, three repeats each. End-to-end includes strategy
execution, original authority validation and comparison recovery. Separate
reference SolverEpisode checks are charged to the suite, outside arm times.

| Strategy | End-to-end min | Median | Max | Execution median | Attempted solve median |
| --- | ---: | ---: | ---: | ---: | ---: |
| Reference | 31.431663 | 31.432674 | 31.461926 | .703524 | .625231 |
| Secant | 30.171207 | 30.216365 | 30.274574 | .701901 | .529929 |
| Frozen AI, OOD fallback | 31.304513 | 31.408830 | 31.430368 | .709837 | .625526 |

Secant-minus-reference paired end-to-end differences were
-1.215298/-1.261468/-1.187352 s. Full authority verification dominates: its
medians were 30.414210/29.236234/30.420246 s for reference/secant/AI, followed by
comparison recovery medians .293167/.278107/.277200 s. These inclusive costs,
including source verification of the selected history, must remain in the result.
The small execution difference is substantially smaller than the total difference.

AI was slower than secant in all three pairs by
1.192465/1.259162/1.029940 s. Its apparently smaller median than reference
(23.844695 ms) occurred while using the same reference starts and paying extra
inference. This is a timing observation, not a learned algorithmic improvement.
Three repetitions in one synthetic geometry on a shared host do not establish
general acceleration.

L300's recorded end-to-end field has min/median/max seconds
1.663385/1.672729/1.698761 (reference),
1.781835/1.787452/1.802631 (secant), and
1.670924/1.672100/1.707336 (AI). These are failed-attempt costs. The field name
and the raw report's arithmetic ratios do not confer successful verification.
L300 skips unavailable full authority replay; its much shorter duration must not
be pooled with L150 into a speedup or complete-suite success claim.
Both raw per-case timing-eligibility flags are true because their source/clock
conditions are valid; L300's complete-path contract is still false. The whole
suite's timing-eligibility flag is false. These different fields must be read
together with completion and authority outcomes.

| Additional measured scope | Wall seconds | CPU seconds |
| --- | ---: | ---: |
| Standalone L150 public API | 31.277392402 | 31.275663205 |
| L150 complete companion attempt, including successful persistence | 10.908060450 | 10.902739413 |
| Standalone L300 public API | 1.691539807 | 1.691445269 |
| L300 rejected companion attempt | .529670211 | .529652555 |
| Whole runtime suite workload | 306.002301503 | 305.982336865 |
| Runtime coordinator API | 307.800561469 | .075346131 parent-only |
| Complete observation driver | 353.267832030 | 45.504680420 parent-only |

The complete driver includes both public/companion attempts, coordinator, interim
source checks and persistence; it excludes imports/initial source checks and
worker CPU. The worker's process CPU through report persistence was
307.580872933 s. Nested scopes are not additive. Three successful episode checks
cost 10.709638213 s; the three unavailable episode checks retained 2,510 ns.
All AI inference cost 46.453711 ms, and L300 failed-seed baseline recovery cost
.707469502 s. Both are already included in the arm/workload totals.

The material timer recorded 116,676 calls over 1.367953826 s, including failed
attempts and guards, with zero exceptions or timing errors in that instrumented
scope. It is a subset of attempted Newton/terminal/guard assembly, excluding
compilation/checkpoint/full J1–J5 verification replays. It is not a separately
additive cost or complete constitutive cost for the whole observation.

One fresh worker PID 469644 retained valid resources despite exit code 2 and
blocked suite status. Whole-worker peak RSS was 131,473,408 bytes
(125.3828125 MiB), from Linux post-exec VmHWM. Strategy/companion-specific peak
RSS and per-strategy CPU are unavailable. Bounded input reads covered 13,204
bytes in .138094 ms; suite JSON writing covered 1,622,418 bytes with
48.993057 ms encoding and 3.151244 ms write/flush/fsync. Sidecar/manifest I/O
and physical disk traffic are outside those file-API scopes.

Environment: CPython 3.10.12, NumPy 1.26.4, SciPy 1.12.0, Linux x86_64.
OMP/OpenBLAS/MKL/VECLIB/NUMEXPR environment values were set to 1. Native thread
behavior and hardware exclusivity are not attested.

## Verification, probes and retained identities

Separate focused groups passed: 30 pure companion tests in 27.73 s, 12 actual
integration tests in 72.66 s and 40 CI boundary/quality-gate tests in .40 s.
The actual integration fixture used one public analysis, one initial companion
inspection and two additional explicit source validations. Pure wrapper tests
used stored/mocked authority fixtures, not additional actual public analyses.
All six changed Python files passed Ruff/format and whitespace checks before
the source commit. This is not a full-suite or hosted verification claim.
Raw test logs, integration artifacts, test/CI sources and scope receipts are
copied under `verification/`; earlier overlapping runs are retained without
adding them to these final counts.

The initial probes at clean `e80241a6362c3b289d271e8820182d4f6482ce72` are sealed
separately in `/tmp/structural-rc-material-probe.iWRotsRB/`. Both public calls
ran once. L150 saved a ready result and complete engineering history before an
auxiliary reporting script used the wrong corotational state nesting and raised
AttributeError. The original exception/log remains; a separate saved-JSON
inspection corrected the aggregation without another solve. L300's original
nonconvergence remains. The probe audit passed 406 checks; its inventory covers
418 files / 8,903,408 bytes, excluding the inventory itself (81,631 bytes, raw
SHA-256 `42cb0157c59f8f84526597504a75b39fdc649e3959ed9c17fc815fcdd387b7d4`).

The current saved-artifact audit passed **682 checks with zero errors** in one
execution. It checked all source/input/raw report identities, public/checkpoint
bindings, every native material field statistic and parent comparison from the
five L150 checkpoint states, all 18 strategy slots and rotated orders, guard
counts and cost arithmetic. Terminal total energy was compared with the original
public result. Intermediate engineering energies/recovery hashes remain bound
stored assertions; this audit did not repeat engineering recovery, Newton,
material integration, inference or training. Neither this audit nor its hashes
provide independent physical V&V.

Selected raw SHA-256 identities are below. The companion's separate logical
report identity is
`sha256:84825a6ce6c65d62631d2d25edf66d834343bbd0cd137b661f8d51d5b7080b04`.

| Relative path | Bytes | Raw SHA-256 |
| --- | ---: | --- |
| `source-before.json` and identical `source-after.json` | 75855 each | `87d45fd5c35ac7f2c784700ba42c4f3e1bb286f5c094751fa530371b940606cf` |
| `inputs/v3-policy.json` | 7628 | `e4cba69ea7c78674fc06542602b6bfaa093d9bf48676369cbf6a7d3023cd7894` |
| `l_frame_150kn/constitutive-history.json` | 28544 | `ff101b0db8bf66560efeb80ade7d5d9a4c299157a96a558734755adf22dc1913` |
| `runtime/suite.json` | 1622418 | `7fac53e79492260e157e41f2d05a4f204e27feea65c61ab80b7c0597f61c9605` |
| `runtime/resources.json` | 2513 | `1b43e4b4af3b8168897ccd6be5d0ad1c1c67a2518f2480c3db02ec842efe5dd3` |
| `audit.json` | 17038 | `c5209058839513ff582285de7685c4a1f7f1483d36d10df4effe6ada325476da` |

The sealed local inventory covers **444 files / 10,700,042 bytes**, excluding
itself. `inventory.json` is 86,151 bytes with raw SHA-256
`3f4c5f37e591e378dda5e74635ecba06a924612c696123b3c299f471fb3dfbcd`.
All inventoried bytes were reread and checked after inventory creation. This
inventory preserves local provenance without a signature or external approval.

The complete M1–M5/P1–P3/R1/R2 objective remains active. Current public history
requires monotonic proportional loading through factor 1.0; decreasing/reversed
loads require a separately versioned receipt/history/input/policy scope and
verification. Yielded/cyclic families, independent corpus and material V&V,
licensing, hardware/operator acceptance, hosted integration and owner/admin
decisions remain open. This local observation grants none of those authorities.
