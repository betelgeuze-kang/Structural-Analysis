# Frozen-source RC durable execution and restart observation

At source `962c302c33d83da7349c9e5871f02fa4fe272549`, the existing 242-target
RC L-frame request completes through the durable service in three fresh
processes: a whole job, a 122-target checkpoint, and continuation of that same
job through target 242. Full and resumed cumulative response/material histories,
all corresponding original core steps, and native restart bytes match exactly.
The observation makes no performance, independent physical-validation, general
cyclic, public J1–J5, design or release claim.

The source snapshot contains 566 tracked files extracted by `git archive` before
execution. The full frozen inventory covers 574 files, including unchanged
inputs, protocol and observer scripts. Each child imports this snapshot through
explicit `PYTHONPATH`; the original checkout and later working-tree changes are
outside the execution. All frozen file identities pass before and after checks.
The original model and complete request are copied from exact Git blobs; target
numbers, two permitted reversals and all solver settings are unchanged.

## Actual execution and costs

| Process | New targets | Prefix replay per invocation | Reserved API invocations | Core target calls | Known Newton iterations / linear solves | Launch-to-exit seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full | 242 | 0 | 2 | 484 | 1,920 / 1,920 | 219.613426641 |
| Prefix | 122 | 0 | 2 | 244 | 1,154 / 1,154 | 101.997680836 |
| Resume | 120 | 122 | 2 | 484 | 1,920 / 1,920 | 223.895565962 |

Totals are **6 reserved invocations, 1,212 original core target calls, 4,994 known
Newton iterations and 4,994 known linear solves**, with zero raised core calls,
pending reservations or unknown solver-work attempts. All 1,212 original
transition recoveries are verified by the existing API. Each chunk reserves its
original analysis and mandatory fresh verification separately. The analysis
entry inside the verifier is not counted as a third reserved invocation.

The serial parent interval is **545.507261007 seconds**. It includes process
startup/import, analysis and replay, observation and serialization, durable
publication, authenticated in-process HTTP reads and retained output. Peak child
RSS values are 1,093,384 / 646,576 / 1,091,916 KiB. Invocation-specific wall and
process CPU intervals are retained separately in the machine summary. These are
observer-inclusive correctness costs; they do not isolate solver performance or
establish a speed comparison. The later saved-data audit and inventory checks
add separate costs and no numerical execution.

There is one launch per slot, no retry and no modified continuation policy.
The prefix job becomes `checkpointed`; a new service process claims the same
immutable request and exact saved checkpoint. Both complete jobs become
`succeeded`. Worker heartbeats renew the real 300-second leases during execution.

## Original artifacts and byte boundaries

- Full job result: **65,675,105 bytes**; resumed job result: **65,680,274 bytes**.
  The durable prefix checkpoint is **118,859 bytes**. Final wrappers legitimately
  differ in chunk receipts, request and invocation costs.
- Both final native restart artifacts are **127,345 bytes**, SHA-256
  `6fc6538139495294d0db7f391acecaa7ea54e4801154b739712424208c2269e3`.
- Both cumulative response histories have canonical SHA-256
  `17a3e06a138c8a58a3e2e8e324354e3b7ff8cac57464f28d99326f6c494c9737`.
  All 242 epochs retain 84 material points and matching original material states.
  The terminal epoch is 242 and load factor is `1.3828147147200147`.
- Authenticated result, evidence and individual invocation reads return the
  exact stored bytes through `DurableJobHttpApi.handle`. This observes the
  in-process HTTP adapter, not a network listener, production identity bridge,
  browser integration or mobile-device memory behavior. At this source, the
  checkpoint has no tenant GET route; the observer reads its hash-checked CAS
  reference directly. Claim requests/checkpoints are retained verbatim and raw
  lease tokens are omitted.

The earlier CLI observation wrote approximately 111 MB of **pretty-printed**
JSON. This service and API use compact canonical JSON. Neither actual durable
result exceeds the legacy **64 MiB = 67,108,864 byte** boundary. This observation
therefore establishes the full 242-target path, not an actual over-64-MiB result
transfer or qualification of the entire 576 MiB configured limit.

The embedded job model uses canonical JSON bytes, whose input checksum differs
from the original indented input file. Both identities remain recorded. Hashes
establish local consistency, not independently authenticated source provenance.

## Saved-data audit and retention

The final standard-library-only audit passes **68,745 checks with zero errors**
in **21.138897010 seconds**, without importing the application or invoking a
solver. It checks frozen input/source identities, original artifact lengths and
hashes, reservation/outcome/journal bindings, exact targets and suffix boundaries,
work subtotals, mandatory verification reports, all core step/restart identities,
all response/material-state rows, retained receipt timings and authenticated
read identities. Physical and release authority remain false.
A separate post-seal read also confirms 970 exact original step/binary-checkpoint
pairs against the full baseline and 1,212 matching journal begin/return pairs,
with zero numerical calls; its receipt and hash are in the machine summary.

The first audit report is retained: 68,739 checks produced 1,215 audit errors.
Its script applied transport JSON hashing to core step hashes, which normalize
negative floating zero, and confused JSON checkpoint hashes with internal binary
state hashes. Correcting these two hash-domain rules resolves the audit errors;
the numerical execution and its original bytes are unchanged. Both audit scripts,
reports and logs are preserved. Core binary checkpoint snapshots retain the
observer's `.checkpoint.json` filename suffix; their content is binary and is
validated by its actual state hash, never parsed as JSON.

Raw data is local at `/tmp/structural-rc-durable-observation.NNmCKutG`:
**3,098 files / 1,275,194,785 bytes**, excluding the inventory itself. Inventory
SHA-256 is
`8662a28b680137b214812777ab6fbd4e5744dce2ecb5ee76c494cf0f9e7c3c0b`.
A separate fresh process verifies the complete file set, lengths and hashes.
The bundle is sealed; GitHub contains this report and the
[machine summary](rc-fiber-durable-observation-20260909.summary.json), not the
large raw bundle. These local `/tmp` paths are retention references, not a
long-term archival or remote availability guarantee.

## Exact-source hosted CI and local follow-up

The final `962c302` hosted snapshot contains **57 successful, 15 failed and five
skipped checks**, including three failed aggregate gates. The previous
`matrix_status_evidence_authority_invalid` exception is cleared: ten preparation
lanes now build the explicitly blocked matrix and stop at
`Internal license due diligence: blocked | inventory=7 | legal_approval=False`.
Full pytest shard bodies and legacy evidence shard bodies do not run. No license
approval or external validation gate is weakened by this follow-up.

The [topology job](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34296474679/job/102294085974)
passes 412 focused tests and the corrected engineering coverage selection:
86 tests at a reported 94%, above its unchanged 90% requirement. Subsequent
coverage selections also pass. It then stops on three mypy errors in two files,
before its later regression neighborhood. The follow-up adds a typing cast at
the already runtime-validated sparse assembly boundary and an explicit optional
equation-count guard. The same hosted selection of **15 source/test files passes
locally**; Ruff and formatting pass. These edits do not change the frozen
observation source and add no numerical calls. New-head hosted acceptance remains
pending.

One [frontend lane](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34296472300/job/102294078768)
passes 406 of 407 tests and fails the mobile Frame3D review's five-second visible
panel wait. The other frontend lane and frontend-contracts succeed. The single
failure is retained and unresolved; it is not silently retried or declared fixed
by the successful sibling lane.

The complete failed-job stage metadata and logs are sealed at
`/tmp/structural-ci962-final._m26n16s`: 36 files / 1,764,608 bytes; inventory SHA-256
`cafadaa73bad9b4562c761251de23d0ddafb98fa116a0bd32801f2b0bf931c29`.
The local type-check result and post-check source copies are included, with a
separate complete inventory verification.

RC Workbench and study integration, larger actual transport sizes, the remaining
hosted failures, broader families and independent validation remain open. Full
M1–M5/P1–P3, current-main R1, separate R2 and licensing/hardware/owner dependencies
remain active; this record does not complete the roadmap or authorize a merge.
