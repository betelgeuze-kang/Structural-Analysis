# Constant-loaded RC full-history runtime pilot

The constant-load study correction is now exercised over the original authored
242-target reversal history on two different topologies. Numerical source
`4a79207f8` is frozen in an observation packet with 429 selected package/schema
and rational-audit files verified against Git. No numerical source is edited
during observation. The public cantilever has -600 kN at N2 in its axial direction;
the L-shaped frame has an independent -0.1 kN vertical load at N3. The latter uses
the earlier base-model and target-history originals. These loads and geometries
are authored diagnostics, not reconstructions of PEER U3 or ARISTA.

All arms use `retained-twofold-refinement.v1`: exact rational strain, native twofold
coordinates, retained material strain, rational assembly and two bounded terminal
corrections. Original Newton polishing is enabled, with unchanged residual 1e-10,
increment 1e-12 m and control 1e-12 m gates. Full response comparisons retain
absolute 1e-10 and relative 1e-8 tolerances. Each arm independently preloads and
then executes all 242 targets. Reference/secant order differs by case, with a fresh
reference run after both. Worker BLAS/OpenMP thread limits are explicitly one.

## Completed pilot and original-record checks

Both reference/secant comparisons pass with zero physical-field mismatches. All
six paths complete; each reference/fresh-reference history and native terminal
checkpoint is exactly equal. Both cases exercise nonlinear material memory:

| Case | Peak absolute fiber strain | Maximum steel accumulated plastic strain | Maximum concrete tensile damage |
| --- | ---: | ---: | ---: |
| Cantilever | 0.0015938297356966225 | 0.0003306055150929063 | 0.9953848019609376 |
| L-frame | 0.006733599384100012 | 0.00975653629047981 | 0.9999999999661977 |

| Case | All three arms: core calls | Newton / linear solves | Reference / secant / fresh-reference path seconds |
| --- | ---: | ---: | --- |
| Cantilever | 729 | 2553 / 2553 | 18.33 / 15.28 / 18.26 |
| L-frame | 729 | 3671 / 3671 | 100.96 / 72.09 / 101.00 |

The pilot totals **1458 core calls and 6224 Newton/linear solves**, including six
preloads. Parent process times are 54.206766402 s and 279.865090108 s; the complete
pilot driver takes 334.084667634 s. Path times include proposal, numerical solve,
original response recovery and step I/O; these nested times must not be added to
parent or driver times. Initial tests and the cantilever audit overlap some pilot
activity, so these are not exclusive-host timings or repeated acceleration proof.

Source `4a79207f8` also fixes the original rational assembly record verifier:
external forces are constant plus load factor times reference forces. Its earlier
formula omitted constants. Fourteen focused tests pass in 11.04 s, including zero,
positive and negative load factors and rejection of a record with constants removed.

Source `6b41880a9` adds `scripts/verify_rc_seed_originals.py`. This separately
reconstructs original preloads and lateral transitions from their original Newton
coordinates, validates native parent chains, recompiles declared constant loading,
replays constitutive assemblies and physical response projections, and recomputes
full comparison and work totals. It also rebuilds rational forces/tangents directly
from original material response records. Newton and new accepted solves are never
invoked by this audit. It is a source reproducibility check, not an independent
physical oracle. The audit explicitly requires complete single-attempt paths;
incomplete or fallback paths need their own retained failure audit before admission.

Five audit tests pass in 2.76 s. They include a real constant-loaded three-target
study with Newton disabled during audit, and refusal of rehashed false preload
responses, missing preload costs, changed tolerances and altered native parents.
Ruff, formatting, one-script mypy using the local source path and diff checks pass.

The complete pilot original audits pass. Cantilever audit cost is 729 assembly
replays and 5832 recorded material integrations in 18.243873866 s. L-frame cost is
729 replays and 61236 integrations in 73.624276354 s. There are 1458 separate
rational record rebuilds, zero new Newton solves and zero state commits. These
audit costs are additional to the numerical pilot, with source recovery still
charged inside each original path.

## Three repetitions are running, not yet accepted

Both complete pilot comparisons and original audits admitted the predeclared
three fresh repetitions per case. A separate driver alternates arm order, uses
the same frozen numerical source and input bytes, and runs an original-record
audit after each completed case pair. It stops on an execution or audit failure;
it does not retry into an existing output directory or alter tolerances.

The active unsealed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-constant-runtime-6fw_tfsz`.
`plan.json`, `source-manifest.json`, `execution-bindings.json`, original pilot
studies/audits, child process receipts, `repeat.py` and per-repeat outputs remain
there. `summarize.py` has been prepared to require all three completed repetitions,
compare original step/history/checkpoint bytes against the pilot and aggregate
full costs and paired dispersion. Its complete positive run is still pending;
there is no final inventory or repeated timing qualification yet. Current task
execution handle `82260` owns the repetition driver; this identifier is a local
continuation aid, not portable evidence of completion.

## Hosted state and remaining work

At published head `3c5dad190`, main CI run 34403375022 fails in `Materialize exact
current-source test evidence`. Repository Python Tests run 34403374976 has two
completed shard failures at that same prerequisite while two shards are still
running at inspection. The three original failure logs explicitly name
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`; they are retained with run/job
metadata under the packet's `hosted-3c5dad190` directory. This is not a new Python
assertion failure or closure of the external prerequisite.

Public experimental source/model correspondence and reuse conditions, independent
campaign training admission, learned net benefit, external verification and the
full M1-M4/P1-P3/R1-R2 objective remain open. This pilot adds constant-loaded,
multi-topology nonlinear runtime evidence without converting internal consistency
or authored damage histories into scientific or release approval.
