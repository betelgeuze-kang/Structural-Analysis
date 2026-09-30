# Cost-pruned layout HTTP admission — 2026-09-13

The immutable RC search HTTP bundle now accepts the separate cost-pruned layout
schemas. It preserves every original decision and every pool model, including
candidates omitted from numerical execution. It distinguishes cost-dominated
candidates from those outside the frozen consideration horizon. Neither group
is labelled physically infeasible. The existing standalone and two-arm graph
formats remain supported.

Admission reconstructs each decision from the frozen plan and preceding original
rows. It rejects future-row incumbents, missing required evaluations, reordered
or altered decisions, inconsistent coverage, changed price identities and claims
of global optimality. The comparison's price table and each row's estimate must
match the original model/quantity/common-price plan; these two checks also apply
to the existing layout formats.

For a verified pruned row, admission additionally checks the original result and
checkpoint hashes, model checksum, complete request including constant loads,
original verification/result binding, analysis/verification outcome and work
records, complete target-step accounting, and performance recomputed from the
original accepted history including preload. An unverified row cannot establish
eligibility. Decision costs must be known and contained in the arm interval.
Coverage and exhaustive cost-optimality audits remain null for this schema.

These are consistency checks on pinned original records, not a new numerical
replay or independent physical validation. A host must still supply the trusted
report pin and authorization. Serving the bundle performs no mutable filesystem
reads after admission. Workbench engineering review of these new schemas is the
next integration step and was not executed in this observation. Subsequent
[Workbench review](rc-layout-pruned-workbench-20260913.md) records that connection,
original downloads and the separately observed legacy-viewer limitations.

## Local verification

The initial regression run passed **187 tests in 154.22 s** across layout HTTP,
layout execution, cost dominance and existing RC search HTTP. Follow-up runs
passed five additional conditions (63.45 s), seven price-binding/acceptance checks
(52.98 s), and four zero-work/preload checks (40.74 s). The last two runs overlap
prior acceptance tests; these counts must not be summed as a disjoint suite.
The last run covers the final complete-step guard. Final-source Ruff, format
checks, focused mypy for three source modules and `git diff --check` passed.

Tests execute actual price-order and learned-order pruned graphs, including a
shortened horizon. They deny solver and fitting entry points during admission
and HTTP delivery, preserve exact immutable bytes and exercise authorization.
Rehashed tampering tests cover decisions, coverage, request, verification, costs,
recorded performance and original work. A fully rebound zero-step record is
rejected even when its result, verification link and invocation hashes agree.
A constant-load case with no feasible incumbent retains all three candidate
rows; its fresh reference verification and HTTP admission both pass. The existing
development-contract workflow already selects this test module. No current-head
hosted or full-repository test pass is claimed.

## Actual loopback delivery

Transport source: `3bc9d7409853d4db81646955f2f9196c695f2f6f`, archived before import.
Numerical input source remains `d11248ce06627c8466ae348a88f91a3b167ce05e` from the
sealed [four-execution observation](rc-layout-cost-pruned-execution-20260913.md).
The observer checked each served original against that packet's pinned inventory.
It admitted both full and both pruned executions and fetched every admitted file
from an actual loopback WSGI server using synthetic tenant credentials.

| Original execution | Original artifacts | Admission time |
| --- | ---: | ---: |
| o0-full | 49 | 0.044856105 s |
| o0-pruned | 38 | 0.129274273 s |
| o1-pruned | 38 | 0.126719791 s |
| o1-full | 49 | 0.036759969 s |

All **174 HTTP responses** matched the original bytes and returned 200. The
transfer/teardown interval was 0.085615955 s. No new numerical paths, policy fits
or predictions ran; these entry points were replaced with rejecting functions.
Admission intervals exclude source archive preparation and export writes. The
transfer interval excludes admission and server startup. These small loopback
observations are not production network, browser or end-user latency benchmarks.
Their costs are separate from the earlier numerical-process measurements.

Read-only packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-cost-pruned-http-qrzs4ei7`.
It contains 818 files / 130,427,614 bytes, inventory SHA-256
`997a747130bd075344a9e7000ee665a5a3b8fcfb2305f7486844f8bd113d481d`.
The frozen source archive, observer, original exported graph bytes and response
receipts are retained. See the [machine-readable summary](rc-layout-cost-pruned-http-20260913.summary.json).

The original reports keep their original claims. This transport change does not
prove learned benefit, independent generalization, global optimality, physical
qualification, release readiness or closure of the wider roadmap. Workbench,
multi-fidelity expansion and independent validation remain open.
