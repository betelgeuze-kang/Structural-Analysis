# RC displacement control and fresh-process restart observation

At clean implementation `f79f3d3b2040f950686509722d5ca0caf7aa148e`, the
experimental small-displacement RC path completed 242 authored targets with two
direction reversals. It retained positive accepted steel plastic accumulation
and concrete tensile/compressive damage. Three separate Python processes ran the
complete path, a 122-target prefix, and its resumed suffix with complete numerical
prefix verification. All 606 planned control calls committed, with 2,497 known
Newton iterations/linear solves, zero unknown-work attempts, failed targets,
unattempted targets or hidden retries. Public analysis requests were zero.

This is internal correctness evidence for one synthetic L-frame and its authored
discretization. It does not establish independent physical or general cyclic
validation, a capacity bound, safe design, performance improvement or release
approval. The original public monotonic-load J1–J5 profile remains separate.
See [the implementation contract](rc-fiber-displacement-control.md).

## Original mechanics and retained development failures

The exact input is `examples/public_rc_fiber_frame_l_frame_material_history.json`,
SHA-256 `9f2a66f86fd5443574032ff4a55f3de09995094808f20c1b7f34ac403de6b59d`.
Nodes are `(0,0)`, `(2,0)` and `(2,1.5)` metres; N3/UY (global DOF 7) is
controlled against the original −150 kN reference tip load. The original
0.4 × 0.6 m section, concrete layers, reinforcement and constitutive parameters
are unchanged. The original assembler has 84 material-point states, including
12 aggregate steel states; this count is not the number of physical bars.
The geometry remains small-displacement throughout.

Both final and development runs use dense original vector Newton with at most
40 iterations, residual tolerance `1e-10`, increment tolerance `1e-12`, control
tolerance `1e-12 m` and load-factor coordinate scale `0.001 m`. The adapter uses
the original accepted parent as its initial guess. No material parameter,
acceptance threshold, numerical authority or physical model was relaxed.

The original 26 waypoints go from zero to −0.02 m in −0.002 m increments, then
to +0.02 m and back to −0.02 m in 0.005 m increments. The initial coarse run
failed at its first −0.002 m target, with exact parent rollback,
`line_search_failed_to_reduce_residual`, control error 0.000861328125 m and
relative equilibrium residual about 0.09973544. A separate target-seeded
initialization variant also failed at the first target: control error zero,
relative equilibrium residual about 8.52958533 and exact rollback. Each retains
one attempted target and 25 unattempted targets. Neither retained accepted steel
plasticity; the seeded variant was not adopted.

The third development protocol retained every original waypoint exactly and
subdivided all intervals **before execution**, using
`ceil(abs(delta) / 0.00045)`: five substeps per 0.002 m interval and twelve per
0.005 m interval, 242 targets total. This changes path discretization and is not
the same history as either failed coarse attempt. The refined run committed all
242 targets in 31.349919982 development wall seconds while other work overlapped.
It is not a comparative performance result. Subsequent numeric-bound,
source-binding and metadata-snapshot hardening did not change its accepted
checkpoint identities in the final observation.

The three development probe roots are individually sealed:

| Root under `/tmp/` | Files | Bytes excluding inventory | Inventory SHA-256 |
| --- | ---: | ---: | --- |
| `structural-rc-direct-control-probe.7ic6c9qu` | 6 | 240,393 | `c0c6c6891285b950fd5805ee62e5bd9664eeb7750e8dc90adf46cc1e6ef8492f` |
| `structural-rc-direct-control-seed-probe.49hiqq9a` | 404 | 8,446,429 | `027c3bfdcdab1da7f8765502ad44dad0d5e9cfce96934bcba90c1a4a481e7294` |
| `structural-rc-direct-control-refined-probe.lvdv8zev` | 646 | 61,880,130 | `b237a2661edb5b14b285aca28d34f277455dbd63f965a26da6f73d9dbb7ee1ee` |

The actual 16-step steel-plastic/unloading test root
`structural-rc-direct-control-step-5sf5wnts` separately retains 18 files,
3,458,079 bytes, inventory SHA-256
`1d9704c8ef0f7458f7530c626634063ba63d3ba27c3ed62aa41fa29be781e18d`.
A distinct process rechecked the complete file sets and all sizes/hashes of these
four roots: 1,074 files and 74,025,031 bytes, excluding their inventories.
The earlier nine failed force-controlled probes also remain unchanged; none of
these new internal results retroactively grants them a public pass.

## Fixed-source complete path and restart

The final observation root is
[`/tmp/structural-rc-control-restart-observation.p_1qvxtk`](/tmp/structural-rc-control-restart-observation.p_1qvxtk/protocol.json).
It retains the clean Git revision's 399 package files, the nine changed
implementation/test/CI/contract files, exact model and protocol, original
per-call step/checkpoint/material bytes and begin/end journals. The wrapper
forwards unchanged core arguments and returns the original step object. Observer
export failures have separate accounting and invalidate an observation without
changing a valid core return; none occurred in the completed execution.

The first launch used Python `-I`, which excluded the existing user-site
`jsonschema` dependency. Import failed before compilation or any core call;
prefix/resume processes were not launched. Original scripts, protocol, trace and
parent records remain in `preparation-failure-01/`. Its parent sequence cost
0.214204272 s. The correction uses the existing normal Python runtime with `-B`
and the archived package first on `sys.path`; no dependency installation or
solver change was made. Runtime versions are recorded in each request.

| Fresh process | New targets | Actually replayed prefix | Known Newton/linear solves | Launch to exit (s) | Process CPU (s) | Lifetime peak RSS (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full, PID 585285 | 242 | 0 | 960 | 72.954895927 | 72.708948772 | 527,687,680 |
| Prefix, PID 585747 | 122 | 0 | 577 | 40.570028009 | 40.304961908 | 320,864,256 |
| Resume, PID 585877 | 120 | 122 | 577 replay + 383 suffix | 74.813193739 | 74.566376886 | 528,592,896 |

The corrected serial parent sequence costs 188.338799060 s. Each process verifies
the source inventory and input identities before/after execution. Whole-worker
cost includes imports, compilation, serialization, per-step sidecar exports,
result checks and any numerical prefix replay. The timed core calls alone sum
to 28.789707050, 17.404400452 and 29.432896328 s respectively; these intervals
overlap whole-worker timing and must not be added again. Observer exports also
overlap whole-worker timing. Earlier 244 development probe calls and all tests
are separate scopes. No repeated runtime comparison, speedup or amortization
claim follows from this correctness observation on a shared host.

The 122-target prefix ends at +0.01 m after the first reversal. Resume performs
all 122 prefix solves from the unloaded state, compares every accepted step
binding and original checkpoint bytes, then executes the remaining 120 targets,
including the second reversal. Both complete restart artifacts contain 127,345
bytes and have SHA-256
`6fc6538139495294d0db7f391acecaa7ea54e4801154b739712424208c2269e3`.
Full and resumed path-result hashes differ because their requested suffix,
initial checkpoint and replay-work scopes differ.

Across the complete path, maximum relative equilibrium residual is
`9.887020010511045e-11` and maximum absolute control error is
`1.0842021724855044e-19 m`, below the original declared gates.
The first positive accepted steel plastic accumulation occurs at epoch 15,
UY = −0.006 m: maximum `7.86764100277988e-6`, load factor
`1.2731521926413412`, checkpoint hash
`sha256:430ea5e72b79511107a63788d7db90cb9bdf4d3876b315493db9fe620f99299d`.
At terminal epoch 242, UY = −0.02 m, the maximum steel accumulation is
`0.009756536290480443`, tensile damage `0.9999999999661977` and compressive damage
`0.13048993532825948`, with load factor `1.3828147147200147` and checkpoint hash
`sha256:6dabcfde2a29021849d606aa48cf4173e7da9b7e6c9ed4bfc640950295f073f4`.
These are accepted internal material variables, not independently verified
damage or capacity predictions.

The [saved-history plot](/tmp/structural-rc-control-restart-observation.p_1qvxtk/accepted-control-history.png)
shows the prescribed response and accepted memory variables. Its script reads
only the saved full summary and performs no numerical analysis.

A separately authored saved-artifact audit passed once in 12.073298082 s, with
zero errors. It verifies 399 source files, before/after input identities, three
PIDs, all 606 begin/end calls and path receipts, known/unknown/replay work,
per-point memory identity/domain/nondecrease, and all corresponding step,
checkpoint and material bytes across full/prefix/replay/resumed execution. It
also compares all 242 accepted checkpoint dictionaries against the original
refined development run, and the full/resumed restart bytes directly. Its
225,303 conditions are repeated low-level field checks, not independent
experiments. This audit does no Newton solve or physical reassembly, does not
recompute native binary state hashes, and is not external execution attestation.
The original execution still performs the existing native state validators.
Report SHA-256 is
`bfc26e63e6ca4847786a0ec688751acfb91f12f3894b618cc199e8bccc51794b`.

After every writer stopped, the final observation inventory sealed 2,284 files
and 300,413,644 bytes. Its own 393,572 bytes are excluded from those totals;
inventory SHA-256 is
`db79f6f3ecf76921fd73e5f0f63b1ee7cb35421d104c1d74e0f723b801bac5a7`.
The sealing process (PID 587368) and separate read-only verifier (PID 587445)
both passed. The latter checks the entire exact file set and every byte size/hash;
its [receipt](/tmp/structural-rc-control-restart-observation.p_1qvxtk-seal-verification.json)
is outside the sealed root. The four earlier development roots have their own
seals above and are referenced by the final provenance report rather than copied
into the 2,284-file count. No later write is permitted within these sealed roots.

## Focused implementation verification

Core tests passed 56 cases in 5.24 s, including the actual first 15 refined
targets and a committed unload to −0.0056 m with retained accumulated steel
memory. Five later nested-metadata regressions passed in 1.90 s, reusing one
small elastic force/control fixture; the 16-step path was not rerun. Final path
tests passed 68 cases in 2.78 s. Original load-control and CI/quality-gate
contracts passed in a separate 133-test group in 13.25 s, which includes an
earlier 56-test path version and must not be counted as 133 additional unique
tests. Ruff, formatting and diff checks passed. Remote CI was not run.

Retained early test failures were a test import/collection error (zero solves),
a fixture assignment to computed `state_hash`, a mismatched graph member ID and
an incorrect assumption that one tiny-target Newton iteration must fail. The
fixtures were corrected without relaxing acceptance. Review also found and
fixed replay/suffix-group mutation, lost accounting for invalid returned steps,
mutable previously recorded receipts and nested result-export aliases. All
twelve requested test logs are copied exactly with source hashes; none is
missing. Initial failed test and probe records remain available.

The full M1–M5/P1–P3/R1/R2 roadmap remains active. Next integration must bind this
experimental profile's full response/material history and restart validation to
public request/result recovery, durable job and Workbench contracts before using
it in verified design comparison or learned candidate studies. Repeated broader
families, independent/licensed material/cyclic references, hardware and hosted
execution, owner/admin decisions and release approval remain open.
