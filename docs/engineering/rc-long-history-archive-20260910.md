# RC history archives with full-prefix restart

Numerical source `e246e4fd541c90c811276716e782e88b7f77a8ac` adds
[`run_rc_fiber_history_archive`](../../src/structural_analysis/execution/rc_fiber_history_archive.py).
It executes an explicitly supplied complete target sequence, publishes each
original attempt and recovered response separately, and resumes by recomputing
every accepted earlier target from genesis. The accepted material state and epoch
continue across targets. Recovery uses the original solver coordinates and the
exact previous accepted state. Cumulative response objects are not kept in memory.

This experimental local profile accepts a declared budget up to 16,384 targets;
that configured bound is not a demonstrated capacity claim. The existing bounded
API retains its 255-target contract. The new profile has no Workbench or durable
HTTP integration. It does not interpret experimental measurements as actuator
commands or add missing materials, reinforcement, loads or sensor definitions.

## Accepted state and retained work

The manifest binds the canonical model, complete targets, solver configuration,
reversal budget and caller-supplied source revision. Each reservation is recorded
before the core call. Original outcomes, reconstruction results, terminal native
checkpoints and all run directories remain available after a failure or resume.
An outcome that is missing remains unknown work. A recovery failure retains its
original core cost and cannot advance the last verified checkpoint. The ledger
inspector counts earlier interrupted runs as well as the successful continuation.

Each entry is published exclusively using an fsynced temporary file and a hard
link; existing accepted entries cannot be overwritten. Unpublished temporary
entries are retained without becoming accepted indices. Callers serialize runs;
there is no multi-writer lease or power-loss durability qualification. Public
hashes and the source-revision field do not authenticate execution. Actual
full-prefix numerical replay checks the recorded responses and original attempts.

## Focused implementation evidence

The implementation-stage combined selection passed **98 tests in 41.69 s**,
including the existing bounded API. After adding preflight-cost and unfinished
publication handling, the final archive selection passed **12 tests in 24.31 s**.
Ruff/format, two-source-file mypy and diff checks passed at that implementation.
Tests include a real 300-target history, interruption after 123 targets, equality
of all resumed responses and final native checkpoint, resealed response
corruption, retained failed-recovery and interrupted-core work, and exclusive
publication. These are focused local checks, not full hosted CI or physical proof.

Initial implementation verification had six test failures and four mypy errors.
Work aggregation discarded a field required by the original count routine, and
manifest comparison treated JSON lists and Python tuples differently. Those were
fixed before the passing selections; the initial run is not credited as success.

A separate four-target diagnostic compares the refactored recovery function
against the original function from `d008a52fbb7bd1d96c59fc00bc3a8bd1b993a4b4`,
using the same current module globals. Both complete API payloads are byte
identical, SHA-256
`bf0860293ed9c9fe3b2a10262bebacb964e94a935e0d54ff92bbefd7c2ee9bd0`.
This diagnostic used eight core calls and 16 Newton iterations across the two
arms. It is retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-recovery-refactor.hewinqv5`;
it is not an independent solver or hardware observation.

## Declared 4,059-target observation

The [committed plan](../../examples/rc_long_history_observation_20260910/plan.json)
declares two authored histories on the same canonical cantilever: monotonic and
cyclic with 20 direction reversals. Each contains 4,059 targets and a 4,096-target
execution budget. Each case runs a complete path, a 1,379-target prefix and a
fresh-process continuation that replays all 1,379 earlier targets before its
2,680-target suffix. Nominal work is **18,994 core target calls** across six
processes. There are no automatic numerical retries or clipped target histories.

The source snapshot contains 592 tracked source files bound to the numerical
commit. Original input, driver, process records, all per-step files and the
separate audit are retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-long-history.m4_fqga_`.
These histories are authored development inputs at the observation length of the
public workbook. They are not the SERA-ARISTA displacement measurements, its
loading protocol, multiple independent structures or a yielding-capacity test.

All six numerical processes have exited successfully. The separate original-record
audit verifies all **8,118 full/split accepted response and attempt pairs** and
reassembles every one of the **18,994 original steps** from its previous parent
using the recorded Newton coordinates. Full assembly, material states and recovered
responses match exactly. All six terminal checkpoints reopen exactly, and each
case's full and resumed terminal checkpoint bytes are identical. All 592 frozen
source files match their original Git blobs and remain unchanged after the audit.

Original work is **18,994 core calls / 37,988 Newton iterations and linear solves**.
It includes the 2,758 repeated prefix targets; there is no unknown core work or
missing recovery outcome in these six runs. The separate audit performs one model
compilation and 18,994 same-law assembly replays, with zero Newton solves or fits.
The maximum replayed relative equilibrium residual is `1.4432899320127036e-16`
and maximum control error is `2.6469779601696886e-23 m`, below the unchanged
`1e-10` relative residual and `1e-12 m` control tolerances. These checks establish
local execution consistency, not experimental fidelity or independent physics.

| Case | Phase | Parent seconds | Peak RSS KiB | Core target calls |
| --- | --- | ---: | ---: | ---: |
| monotonic | full | 116.098816 | 109408 | 4059 |
| monotonic | prefix | 40.699087 | 108860 | 1379 |
| monotonic | resume including prefix replay | 118.149456 | 110432 | 4059 |
| cyclic | full | 119.349447 | 109284 | 4059 |
| cyclic | prefix | 40.780147 | 109376 | 1379 |
| cyclic | resume including prefix replay | 119.143081 | 110348 | 4059 |

The original numerical-suite parent takes **554.221669 s** and the successful
audit child parent takes **215.307600 s**. Their sequential sum is **769.529269 s**,
excluding preparation, coordinator work, the failed audit, the separate refactor
diagnostic, inventory and publication. It is not total project cost. Nested core
and recovery times are reported separately in the
[machine summary](rc-long-history-archive-20260910.summary.json) and must not be
added again to parent times. Coordinator work shared the host; these observations
do not establish a performance comparison or deployed latency.

The first audit attempt used the archive JSON hashing rule for the native step
hash. The latter normalizes signed floating zero, so this audit stopped before
its first numerical reassembly. Its script and failure log remain intact. It
completed 4,059 full/split record comparisons and one model compilation, with
zero Newton solves or fits; its elapsed time was not recorded and remains
unavailable. The corrected audit uses the documented native hash rule without
changing original records or restarting the numerical suite.

After checking that all original children and recorded drivers were absent,
**73,876 files / 815,771,088 bytes** were inventoried and reread exactly. Inventory
SHA-256 is `7f8409d066929ebd7f47a670af3827ddf1b6a78d80485232c3f820581b3a622b`.
Both audit scripts, the first failure, successful audit, original process records,
inputs and frozen source are retained. The first audit's missing elapsed cost is
explicit, so complete all-activity timing is not claimed.

## Remaining roadmap work

Public experimental model reconstruction, independently grouped training and
unseen evaluation, measured-model comparison, yielding and broader material/3D
coverage remain open. Learned warm starts still need to beat the strongest
deterministic baseline with full costs. Workbench/multi-fidelity integration,
current issue-state and supplemental-artifact integration, full CI, independent
validation and owner/administrator/licensing/hardware dependencies are not
closed by this local archive observation. No speedup, design authority or release
approval follows from it.
