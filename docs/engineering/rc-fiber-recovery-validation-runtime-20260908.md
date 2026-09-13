# RC engineering recovery validation cost — 2026-09-08

At fixed clean source `09df0c9ca0ecada5eb722f9eb4a1fbc97af58306`, one two-step
public RC request took 4.161425281 seconds, compared with 9.722951670 seconds at
`5217e2b6ea76d0c28555ccf13e8c36eb5672e810`. Result, checkpoint and complete
committed-state history bytes matched the baseline. This is a bounded local
before/after observation, not a repeated multi-family performance study.

## Change and verification boundary

The public API and runtime benchmark now create the engineering result and its
recovery operator together. Within each synchronous recovery operation, private
helpers reuse the adapter that the operation has just fully validated. A newly
built operator already independently replays the terminal constitutive, section,
element and global assembly transition; its builder checks physical gates,
immutable array storage, descriptors, source bindings and hashes before returning.
Rebuilding the same new operator again added no different physical check.

Caller-supplied operators still undergo shape validation and a new independent
engineering replay, with metadata and every retained array compared. Both public
validators and both `to_manifest()` methods still validate the entire source anew.
The source adapter must be the same retained instance; matching hashes alone do
not authorize substitution. Engineering result type, profile, ID, source/operator
identity, bindings and hash checks remain in place.

There is no persistent cache, validation token or public skip flag. Retained
Newton dictionaries and some source arrays are mutable despite frozen outer
records, so success from an earlier call cannot authorize a later call. This
change does not claim atomic authentication against concurrent source mutation.
The adapter and terminal validators themselves, solver, tolerances, schemas,
default backend and history recovery were not changed. Deeper adapter-internal
source replay remains and is included in the measurements below.

## Protocol

The unchanged input is `tests/fixtures/fiber_frame_candidate_process/base.json`,
copied as 2,040 original bytes, SHA256
`783a572823311ea2614e2df0207109d16bd4e8e2fb2a96240c77ecaacb505ea9`.
Configuration: two load steps, residual tolerance `1e-10`, increment tolerance
`1e-12`, maximum iterations 40. Both runs used Python 3.10.12, NumPy 1.26.4 and
SciPy 1.12.0 on the same local host.

Each source version received three new public analysis requests: one ordinary,
one instrumented with cProfile, and a separate ordinary request followed by the
whole-history accessor and independent history validation. Thus this observation
made six public requests in total, separately from regression-test solves. It
performed no training, candidate suite or benchmark-worker run. Other owned tests
and source edits were stopped during measurements. Both drivers checked the
expected clean HEAD, input and 394 tracked source/schema/package files before and
after execution. Between versions, only the three intended production files
differed in that source inventory.

The construction driver was copied byte-for-byte (SHA256
`4fea989803550c4eaec502b29e10f296f26b92705e318a0a6cbed3afd7838de1`), as was the
history companion (`6106f1b64d04b5db75b03999c263fc00dde0d57410996ccad0e476fccdfe11ee`).
The ordinary construction interval covers the complete public analyze call,
including its verification. It excludes imports, input parsing, subsequent public
validation, serialization and file writes. The history intervals below are
additional operations and are not included in the construction interval.

## Observed time and work

| Observation | Before | After |
| --- | ---: | ---: |
| Ordinary public analyze wall, seconds | 9.722951670 | 4.161425281 |
| Ordinary public analyze process CPU, seconds | 9.722407720 | 4.161200725 |
| cProfile-instrumented analyze wall, seconds | 20.349479274 | 8.607083408 |
| Separate history companion's analyze wall, seconds | 9.852291862 | 4.167887782 |
| Whole-history accessor wall, seconds | 1.230506412 | 1.237674371 |
| Independent history validator wall, seconds | 1.227920054 | 1.255347081 |

The first ordinary wall comparison is 57.19998% shorter. These are individual
observations, not estimated medians or confidence intervals. cProfile timings
include substantial instrumentation overhead; inclusive function intervals
overlap and must not be summed. History-only timings show no improvement here.
This observation does not measure peak memory or disk traffic.

The instrumented API call gave the following actual counts:

| Function boundary | Before | After |
| --- | ---: | ---: |
| Full load-path execution, including original solve | 34 | 14 |
| Terminal source validation/replay | 33 | 13 |
| Numerical adapter validation | 7 | 2 |
| Recovery operator build / terminal engineering replay | 4 | 1 |

The original solve remains one call; the reduction is in repeated verification
work. A single adapter-validation entry still contains multiple internal source
replays. This is not evidence that learned warm starts outperform deterministic
starts, and does not change earlier negative or mixed learned-policy observations.

## Exact output and regression checks

Both instrumented and ordinary runs passed the public authority contract.
The root independently compared before/after result JSON, public validation,
checkpoint bytes and complete history, including the instrumented outputs.
The public result hash stayed
`sha256:3a82f982807624f68ad4301797aebcbe5c6c05db822860af7dbb110f69752132`.
Raw output SHA256 values are:

| Artifact | Bytes | SHA256 |
| --- | ---: | --- |
| Result JSON | 12,551 | `70726d0c9708636b7d9c5e955b4c4f61bd4ccbd2cc492741467fa570cf69ee46` |
| Checkpoint chain | 12,484 | `2727e0b9c5e30339684f5c1649fae11650e82ae6b0334c4f1e7cc411dd11b77a` |
| Complete history JSON | 89,973 | `8ccec65f33c4a49d8e9665b3a1f992f4978fbad4e65a197e96c9c2f8e7fdf26b` |

Focused verification before the clean source commit:

- Recovery module: 27 passed in 229.06 seconds, including 18 new cases. Seven
  public entry paths count real adapter validation and engineering replay;
  direct/supplied-operator construction preserves all 21 artifact arrays.
  Equal-hash foreign source instances, fully rehashed one-ULP array changes,
  retained early-epoch mutations after prior success and invalid adapters are
  rejected. The rehashed array first passes shape/hash validation and is then
  rejected by independent replay.
- Adjacent adapter, terminal receipt, history, public API/restart, runtime
  benchmark and conditioned-input routing: 82 passed in 154.95 seconds.
- All four changed Python files passed Ruff lint/format and `git diff --check`.
  Two independent code reviews found no unresolved defect in this slice.

The two test groups are separate executions. No frontend source changed, and
this slice does not claim a new frontend, full-repository or hosted CI run.

## Preserved observations and remaining scope

Baseline: `/tmp/structural-rc-recovery-baseline.2eDPnz/`. Its inventory contains
28 files / 2,369,613 bytes; the inventory itself is 5,039 bytes with SHA256
`199ec6da2d9db883a748ad644a60664e30c26020cc7524299268cddedf9fa7ff`.
The source snapshots, full profiler records, exact outputs and drivers remain
preserved. The after observation is `/tmp/structural-rc-recovery-after.b0ohj0ie/`.
Its inventory contains 32 files / 2,400,290 bytes; the inventory itself is 5,871
bytes with SHA256
`d57d427abb88696997b44556bebc5a991ad813b55909863b09799822a12d3ee4`.
`audit.json` records 57 passing checks, including 13 raw-byte comparison pairs,
source inventories and the two driver/configuration identities. `verification/`
retains both test logs and a byte-identical copy of the baseline inventory.
The root rechecked every file's length/hash and the complete file sets in both
directories after sealing; both inventories passed and the baseline was unchanged.

These local hashes bind preserved bytes; they are not independent numerical or
operational acceptance. Remaining source-replay cost, repeated multi-case
performance, independent validation/corpora, public scale expansion and hosted
integration remain in the roadmap. No protected evidence, remote branch, PR,
issue state or release status was changed.
