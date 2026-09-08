# Extended sparse accepted states and durable review

At implementation commit `e3059804889d7f1af928c1f8bd6fef326e39c91d`, the explicit
`scipy_sparse_splu_cpu_exact_1536` planar load-control path retains complete CSR
accepted states through J4 source validation, engineering recovery and checkpoint
prefix replay. The durable v1 request accepts that backend, and Workbench checks
its published backend/diagnostic contract before exposing the existing read-only
engineering identity and authority projection.

The actual 258-equation observation uses substantially fewer stored global-matrix
array bytes, but takes longer including validation. It is not an acceleration
result or independent structural validation.

## Storage and acceptance

The new `stateful-corotational-fiber-frame2d-sparse-state.v1` contract uses storage
profile `member-scatter-canonical-csr-fp64.v1`. It retains the free Jacobian and
global material, geometric and consistent tangents as immutable canonical CSR
arrays, together with physical vectors, member responses and material states.
Member matrices remain at most 6 by 6. Detached SciPy exports cannot mutate the
stored arrays; CSR dimensions, sorted unique indices, finite values, immutable
backing, counts and hashes are checked. No compatibility property silently
materializes a global dense matrix.

Each accepted sparse epoch is bound into J4 by schema, storage profile and
assembly hash. Validation connects the original Newton coordinates, residual,
parent, accepted child, target load factor and child material states, then
reassembles from the exact parent before comparing the full accepted assembly.
Terminal engineering recovery also uses the original Newton coordinates and CSR
assembly. A self-consistent storage hash does not replace physical source replay.
Failed steps retain the exact parent checkpoint. A prescribed-only system keeps
its no-Newton contract. Empty low-level systems retain CSR/CSC/COO/DOK/LIL
compatibility.

Default dense and the existing 256-equation sparse backend keep their former
dense accepted-state serialization. The native sparse Newton v1 receipt remains
unchanged. The strict `1e12` condition, `1e-14` pivot and `1e-12` backward-error
limits, convergence tolerances and zero fallback/regularization policy remain.
Public topology is still 2–128 nodes and 1–256 members; 1,536 is an algebraic
diagnostic limit, not a new public structural-model size.

## Fixed-source compatibility and resource observation

Before and after sources were separately exported from commits
`8eb445519043a58eb083d4e127743ec323825ca0` and
`e3059804889d7f1af928c1f8bd6fef326e39c91d`. Each small-portal capture makes three
new public requests: dense, existing sparse and extended sparse, each with two
load steps. The before/after dense and existing-sparse result JSON, validation JSON
and checkpoint files are byte-identical. Extended sparse retains exact checkpoint
bytes and all five public SI row groups. Its new accepted-state/J4 bindings change
the engineering and outer result identities, so its whole result and validation
JSON are deliberately not claimed byte-identical.

Separate fresh processes use the same 88-node, 87-member model, with 258 free and
264 global DOFs, at load factors 0.5 and 1.0. Input SHA-256:
`d6b1b6d449cbaa6c70f20ab263b672dd15e3f1a2db0e86543554a8f0732d0164`.
There is one ordinary before request and one ordinary after request, in that
order, followed by a separate guarded after request. There is no fitting, warmup,
repeat distribution, altered physical tolerance or independent solver reference.
Internal validation/source replays are included in each request's measured cost
and are not counted as extra top-level requests. The six small compatibility
requests and the three large observation requests are separate from test runs.

| Observed quantity | Before | After |
| --- | ---: | ---: |
| Validation-inclusive wall time, seconds | 30.766834941 | 140.417774206 |
| Process CPU in that interval, seconds | 30.764843089 | 140.409315266 |
| Process lifetime peak RSS, bytes | 181,805,056 | 164,720,640 |
| Four retained global-matrix arrays per accepted step, bytes | 2,205,216 | 137,520 |
| Those arrays across two accepted steps, bytes | 4,410,432 | 275,040 |

The timer covers `analyze_planar_frame`, public result validation, conversion of
the validation and result to dictionaries, and checkpoint retrieval. Imports,
input parsing, source hashing, JSON encoding/file persistence and array accounting
are excluded from wall/CPU time. A wrapper retains the original producer path in
both runs without changing numerical work. Linux `ru_maxrss` instead covers the
whole process through post-run accounting, including imports, retained path and
JSON work. It is not a per-phase peak or a sum of array sizes. Other owned solver
and browser tests had finished before these sequential observations; this is
still one local observation per source with no controlled hardware qualification.

The selected matrix arrays decrease by about 93.76%, while wall time increases
about 4.56 times. Peak RSS is about 9.40% lower in this pair. These observations do
not establish general memory scaling or speedup. The new per-epoch source replay
and repeated storage/scatter validation are included in the slower run; no
profiling attribution to individual functions is asserted. Local/member arrays,
Python objects, serialization and factorization storage are outside the selected
matrix-byte inventory. The ordinary after source and input hashes remained
unchanged across execution.

The separate guard probe blocks known global dense assembler aliases, CSR/CSC/COO
`toarray`/`todense`, and square `numpy.zeros/empty/ones` allocations larger than
6 by 6. It converged with no blocked call and all public contracts passing. Its
whole result, validation, checkpoint and accepted-state inventory files equal the
ordinary after run byte-for-byte. This guard observes those Python paths; it does
not inspect allocations
inside native SuperLU or prove a bound on sparse fill-in. Guarded elapsed time is
diagnostic and is excluded from the before/after timing comparison.

## Durable and browser verification

The existing worker/HTTP/service implementation required no change. The actual
fixture calls `DurableJobHttpApi.handle` directly to submit the extended request,
saves one step, reconstructs the service,
retains a failed resumable state and checks optimistic checkpoint binding before
resuming the suffix. Terminal checkpoint bytes and all SI/engineering rows equal
the uninterrupted two-step result. This exercises durable service reconstruction;
it is not a process-kill or deployed-service observation.

Exact status/result/evidence GET bytes and provenance are checked in under
`tests/frontend/fixtures/extended-sparse-durable-job/`. Workbench requires complete
typed planar metadata, the selected 256/1,536 policy hash, diagnostic counts and
history dimensions, strict quality summaries and consistent no-solve metadata.
Missing metadata, inconsistent backend/policy/storage declarations, cross-type
promotion and hash-mismatched raw artifacts are rejected. Browser checks use those
actual Python bytes behind mocked same-origin GET routes with a synthetic test
cookie; they do not exercise live backend authentication. The browser checks
stored service-report consistency and byte bindings, without numerical/source
replay or authentication of coherently resealed arbitrary artifacts. Desktop/mobile
render identity, authority and committed progress; this panel has no physical
tables or planar artifact-download controls, and the tests do not claim otherwise.

## Verification record and limits

These are separate, partly overlapping groups, not a repository-wide test total:

- Sparse state/native assembly: 72 passed in 8.03 seconds.
- Final public no-dense/source/restart/rollback integration: 10 passed within the
  review-fix run. Five additional empty-format assertions initially used an
  upper-level metric name; after correcting that test assumption, the complete
  extended Newton module passed 15 tests in 1.66 seconds.
- Existing solver/J1–J5/general/recovery/public/258-equation neighbors: 144 passed
  in 409.21 seconds. Final target-binding and empty-format fixes were separately
  covered as above; the neighboring process imported the earlier candidate.
- Final durable source: 30 passed in 13.51 seconds. Initial fixture setup retained
  one step before using the wrong retry state. An earlier successful fixture ran
  four authored steps; the final source fixture ran four more. All nine
  authored-step counts are recorded in provenance; internal checkpoint/source
  replay is a separate scope.
- CI ownership/quality-target contracts: 40 passed in 0.45 seconds.
- Trusted Node 24.20.0 TypeScript, Vite build, delivery contract and final complete
  Workbench run: 307 passed in 58.6 seconds. An earlier whole run passed 306 and
  hit a five-second display timeout in an existing candidate comparison test
  while another browser group ran. After the other group stopped, the same source
  and time limit passed the whole run. A concurrency cause is not established.

Review also corrected a missing child/step target binding and empty DOK storage
compatibility. The initial mobile/desktop checks assumed one status GET despite
development StrictMode retrying it; their request-path set and GET-only checks
now retain the actual contract. Final focused browser checks passed 26 consumer
contracts plus three real Chromium render/tamper cases. No production timeout,
solver tolerance or numerical acceptance criterion was weakened.

The exact-source exports and small/large observations are retained under
`/tmp/structural-sparse-state-before._2ymdbi1/` and
`/tmp/structural-sparse-state-after.0660y6j3/`. The reusable driver is
`/tmp/structural-sparse-path-observation-driver.eoxemcie/observe.py`.
The separate local audit passed 83 checks, including 33 large-run artifact
hash/length bindings, exact SI rows, convergence history, physical array bundle
and descriptors, and all three small-backend comparisons. The large checkpoint
is 1,434,697 bytes with SHA-256
`aad653633aaa3ce3c129fa61ef4fb59514c54578e9e7b2da0372787f960ebfcf`.
The large-run raw files retain downstream adapter/engineering bindings and
accepted assembly hashes; standalone J4 stage receipts were not saved, so the
audit does not claim a direct comparison of those stage hashes.

Both complete file sets were rehashed after writing `sealed-inventory.json`.
Counts and totals exclude that enclosing inventory itself; files inside include
the nested per-run inventories. These are local consistency records, not signed
provenance or external numerical verification.

| File set | Files | Total bytes | Enclosing inventory SHA-256 |
| --- | ---: | ---: | --- |
| Before | 600 | 14,067,034 | `5700ad69a77738e49fac6ae059b2658da0ed46ae002a382c81398da90af73db2` |
| After | 448 | 22,135,458 | `3e9ad5a9a9acd0d55754e1cfd1ef5c7ce36992c99f727c42debe167d6a4f4f97` |

The after set includes `independent-plain-audit.json` (27,437 bytes, SHA-256
`12a76e860986a79cc90bb6f7595adde027261ba97650c2cf42111edea14bbe2b`),
the exact driver, preserved test logs and two browser images. The roots contain
different accounting/source artifacts and are not comparable memory quantities.

Independent OpenSees/second-solver evidence, broader scale qualification, hosted
exact-head CI and remote review remain open. No push, PR, merge, deployment,
release or physical/design authority promotion was performed.
