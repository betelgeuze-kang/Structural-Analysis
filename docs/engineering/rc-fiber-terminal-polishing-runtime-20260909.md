# Damaged L-frame runtime with optional terminal Newton polishing

At frozen numerical source `936e230cec9942e10121273fed7fab336579e3bb`, all
18 declared strategy paths pass their own J1–J5 verification and the unchanged
full-history comparison, and all six reference-episode checks pass. The interior
learned arm is faster than deterministic secant in all three paired repetitions,
by a median 0.414968981 s. The load-OOD arm uses reference starts and is slower
than secant in every pair, by a median 0.875481976 s.

This is a local result for two evaluation cases in one synthetic damaged L-frame
family. The original failed study at `24e34255649ced519991a60904efae6621f49e3c`
and its 15/18 comparison result remain unchanged. The new observation evaluates
an explicit numerical option applied equally to reference, secant and learned
arms; it does not retroactively pass the previous experiment. See
`rc-fiber-terminal-polishing.md` for implementation, request versions and tests.

## Frozen protocol

Observation root: `/tmp/structural-terminal-polishing-observation.2N0cNDVG/`.
The source manifest binds 397 package files (261 Python and 136 JSON files).
The protocol binds the original two model files, public configurations, frozen
policy and execution scripts before the new numerical work. Inputs, source and
scripts match their recorded identities after both child processes exit zero.

The policy artifact remains
`sha256:73def809586df6331a3d8977a216887c0f60a6d9d8145132d39b062e924baeca`.
No new collection or fit occurs. The six original collection cases produced
24 accepted samples, with only 16 train rows used in fitting. Caller-declared
synthetic train/validation/holdout groups do not establish independent projects,
an unseen geometry family or an externally licensed corpus.

The `rc-fiber-runtime-process-request.v2` selects `terminal_polishing: true`.
Both `validation-static-interior` and `holdout-load-ood` retain four load steps,
residual tolerance 1e-10, increment tolerance 1e-12 and maximum 40 iterations.
Response comparison remains absolute 1e-10 and relative 1e-8. Three repetitions,
zero warmups and the stock rotating three-arm order produce 18 selected paths
and six separate reference-episode checks. The protocol forbids retries,
case substitution, refitting and tolerance adjustment after outcomes.

The observer retains the same typed results returned to the stock suite worker.
It does not replace numerical routines or clocks. After stock suite/resource
persistence it serializes all 18 paths, comparison snapshots and bindings into
54 files. This export adds no solve or physical recovery. Retained arrays affect
whole-process memory; these measurements cannot establish per-arm memory savings.
Hardware exclusivity is not verified.

## Default preservation

A separate process first made one default public analysis of the original
interior model. Its public JSON (57,229 bytes) and checkpoint (149,453 bytes)
exactly match their prior retained bytes. The new benchmark ran only after this
check passed. This establishes default parity on one known input, not every
supported model or independent physical accuracy.

| Default-check scope | Wall s | Process CPU s |
| --- | ---: | ---: |
| One public request including original full recovery | 29.894172683 | 29.891938011 |
| Child launch to exit | 32.103270871 | unavailable for this exact interval |
| Child lifetime through byte check | unavailable | 31.892167258 |

The parent launch/wait CPU is 0.007797545 s; child post-exec peak memory is
116,842,496 bytes. These are additional correctness-check costs, separate from
the measured polishing arms and historical training.

Public SHA-256: `871e8f607298f4ce9c29739b29231c7b97fc017ba887e3e64e4ebbcf4ef34784`.
Checkpoint SHA-256: `266724b792fc59537b213a40eb6ea2c34ede4593c9ff5d1f58bd54386982f39f`.

## Full comparison and repeated timing

Both cases are `ready`: 9/9 full paths and 3/3 reference episodes per case.
Independent arithmetic over the saved comparison snapshots reproduces all
18 full comparisons with zero violating displacement, material-state or trial-
response leaves. This saved-data audit does not rerun physical J1–J5 recovery;
the original worker's source-bound recovery results remain the authority.

The three interior learned paths have maximum absolute displacement difference
1.0842021724855044e-18 and material-state difference 5.551115123125783e-16.
Their aggregate trial-response maximum is 1.1641532182693481e-10, and all
elementwise checks pass with the unchanged absolute-plus-relative rule.
Trial fields have mixed units and scales: comparing their aggregate maximum to
the absolute tolerance alone would misstate the result. Interior secant/learned
checkpoints differ in bytes from reference despite full tolerance parity.

All 12 interior learned seeds pass the physical guard at damping 1.0 and are
committed, charging 24 guard assemblies. Across all 72 load-step attempts there
are no failed seeds or baseline recoveries. Stored terminal material states
retain positive concrete tensile damage: interior maximum 0.8440122564222088
with eight of 72 concrete points positive, and OOD maximum 0.991035274998446
with 23 points positive. Positive counts repeat across all strategies/repetitions;
the OOD maximum ranges from 0.9910352749984459 to 0.991035274998446 (one ULP).
The interior maximum repeats exactly. Steel accumulated plastic
strain and concrete compressive damage remain zero throughout the saved paths;
this adds no steel-yield or cyclic qualification.

All repetitions are retained below. Each number is the stock
`verified_end_to_end_wall_ns` converted to seconds: attempted execution, guards,
polishing, original authority/recovery and comparison are included. Separate
reference episodes, default parity, training and later export are outside this
per-path field and remain charged in their own scopes.

| Case | Arm | Rep 0 s | Rep 1 s | Rep 2 s | Median s | Newton iterations per path |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Interior | Reference | 30.144986262 | 30.340755237 | 30.251119979 | 30.251119979 | 21 |
| Interior | Secant | 28.745515130 | 28.872649671 | 28.828658113 | 28.828658113 | 17 |
| Interior | Learned | 28.330546149 | 28.428151747 | 28.643146531 | 28.428151747 | 15 |
| Load OOD | Reference | 33.254414444 | 33.243287141 | 33.204864308 | 33.243287141 | 27 |
| Load OOD | Secant | 32.141773834 | 32.133873880 | 32.259900232 | 32.141773834 | 24 |
| Load OOD | Learned fallback | 33.017255810 | 33.416051456 | 33.131418183 | 33.131418183 | 27 |

Interior learned-minus-secant paired differences are -0.414968981,
-0.444497924 and -0.185511582 s (median -0.414968981 s). Learned-minus-reference
is negative in all three pairs, with median -1.814440113 s. The difference
between the two arm medians is a different statistic and is not substituted
for the paired median. This provides a measured benefit against secant on this
one in-range synthetic case under the shared polishing option.

All 12 OOD learned proposals abstain with `policy_reported_ood` and use reference
parent starts, with no seeded attempts or guard assemblies. All five genesis/
accepted checkpoint byte sequences match reference exactly in each repetition.
Learned-minus-secant is +0.875481976, +1.282177576 and
+0.871517951 s. Against reference, the paired differences change sign
(-0.237158634, +0.172764315, -0.073446125 s). This is fallback overhead/variation,
not useful learned prediction on an unseen load history. Three repetitions in
one family do not establish a general speedup, statistical reliability or a
reason to enable the research option by default.

## Additional Newton work

Across the 72 direct strategy load-step attempts, excluding duplicate selected-
path records, 51 polishing candidates are accepted and 21 rejected. They incur
72 additional assemblies and 51 candidate backend solves, with no recorded
assembly or backend exceptions. These counters exclude both the paths' J1–J5
authority replays and the six separate reference-episode replays; they are not
complete replay-inclusive numerical call counts. Authority replay cost remains
in per-path verification, and all replay cost is included in whole-suite wall/CPU.
Candidate costs are nested in the existing attempt/assembly/backend totals and
must not be added a second time.

All 21 rejections record `strict_residual_improvement_not_met`: each charges
one candidate assembly and zero candidate backend solves, retaining the original
converged state. No case fails its complete path because polishing is rejected.

| Case | Reference accepted/rejected | Secant accepted/rejected | Learned accepted/rejected |
| --- | ---: | ---: | ---: |
| Interior | 9 / 3 | 9 / 3 | 6 / 6 |
| Load OOD | 9 / 3 | 9 / 3 | 9 / 3 |

Selected iteration counts include accepted polishing history rows. Rejected
work stays charged without adding a selected history row. Comparing these
iteration totals directly with the previous unpolished study would confound
the changed numerical option and does not measure its isolated overhead.

## Whole-process cost and saved evidence

| Scope | Wall s | Process CPU s |
| --- | ---: | ---: |
| Runtime child launch to exit | 586.484523098 | unavailable for this exact interval |
| Stock suite workload, including reference episodes | 580.791805422 | 580.725541876 |
| Observer call around stock worker | 580.874542876 | 580.801299891 |
| Observer preparation | 1.700086584 | 1.686604309 |
| Post-worker path/snapshot export | 3.712571087 | 3.566445390 |
| Observer main interval | 586.309943257 | 586.077088341 |
| Worker lifetime through stock persistence | unavailable | 582.513574301 |
| Worker lifetime through observer checks | unavailable | 586.103428773 |

These intervals overlap; they are not additive. Runtime parent launch/wait CPU
is 0.136471364 s. The two sequential default/runtime child wall intervals sum
to 618.587793969 s, excluding intervening parent checks and preparation.
Whole costs for parent imports/source checks and later audit/sealing remain
unavailable. The historical six-case generation plus full training cost
179.720714450 s remains recorded in the preceding sealed experiment; policy
reuse does not erase it. No cumulative research break-even is observed here.

Stock Linux post-exec VmHWM is 133,033,984 bytes, increasing to 138,022,912 bytes
after export. Peaks overlap and include retained arrays and interpreter/import
costs. They are neither summed nor allocated to individual arms. Bounded input
reads total 35,552 bytes in 146,626 ns; suite output is 1,808,085 bytes with
55,450,617 ns encoding and 8,080,344 ns write/flush/fsync time. The 54 later
path/snapshot/binding exports total 48,404,490 bytes. These are scoped logical
I/O observations, not complete physical disk traffic.

`saved-audit-01/audit.json` passes 2,455 checks with zero errors. It checks
source/input/script identities, original policy/default bytes, all 18 saved
path/snapshot bindings, elementwise comparisons and cost arithmetic. Its
`new_solver_calls`, `new_recovery_calls`, `new_fit_calls` and `new_worker_calls`
are zero for the saved audit only; the observation itself performed the
declared default analysis, benchmark and reference replay work.

The evidence root retains preparation/execution/audit logs, all 11 focused
test logs including initial failures, frozen scripts and raw artifacts. Test
groups and corrected failures are described in `rc-fiber-terminal-polishing.md`;
they are not summed into an inflated unique-test count or an exact-head full
repository/hosted test claim.

| Raw file | Bytes | SHA-256 |
| --- | ---: | --- |
| `protocol.json` | 6,018 | `9e3485247c37bf9d6e2085d08eb4071d904e257aa35cd04c8c78418e83fc268b` |
| `worker/suite.json` | 1,808,085 | `f5b00060ba52382ef681df94898f82f3738dec9b9de9fb7e33b1069980bf4baa` |
| `worker/resources.json` | 2,553 | `44d01d181904cc34316c37e09353ecb01ac73a056b05bf436e3afcaa84f04729` |
| `observation-sidecar.json` | 152,323 | `6b3d151dcede37ff7fd728fc8323407d178a19d93444f1c6de7badb52a8a4ee9` |
| `execution.json` | 713 | `67ac85746d02a746869ef56e06e25d1e1d95b9420a50f0f6bf767586b9450448` |

The completed observation inventory binds 503 files totaling 59,170,573 bytes,
excluding `artifact-inventory.json` itself (100,531 bytes, SHA-256
`67a4aa4a6a86e7da1ea7fa9c12470f6f30f9ed88ced942f58329debdf742e5b0`).
Creation and a separate read-only verification both pass exact file coverage
and every file hash. The original failed experiment also retains its verified
476-file inventory and unchanged manifest SHA-256
`d5b55ccf4cfb225975052da10bfba4e965f9c86d0ff19ef6f62148a5afeb9023`.
No file in either observation root is changed after this verification. These
local hashes detect subsequent byte drift; they are not signed attestations.

## Remaining scope

The previous failed experiment is preserved as failed evidence. The new local
comparison and timing result closes this declared observation only. Independent
licensed corpus, steel-plastic/cyclic coverage, hardware/operator qualification,
broader numerical verification, hosted integration, design-code authority and
release approval remain open. The M1–M5/P1–P3/R1/R2 roadmap remains active.
