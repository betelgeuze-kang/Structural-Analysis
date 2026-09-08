# AI design exploration implementation register

Started 2026-09-08 from main `4de4e3f55aae1d267cf704cec7d7533f3a627498`.
The owner requested sustained implementation of the agreed roadmap. This file
tracks development work, not product readiness or external verification credit.
The product objective remains in `ai-nonlinear-cost-workbench-plan.md`.

| ID | Deliverable and acceptance | State |
| --- | --- | --- |
| M1 | Multiple supported physical cases; reference/secant/optional learned arms; repeated timing, dispersion, full history/recovery and failure coverage; immutable experiment identity and separate timing | suite, increment/material trial timing and fresh-process CPU/RSS/file-I/O wrapper implemented; 18-run learned study, 8-run increment observation and new 12-run CPU/RSS/file-I/O observation passed; whole-study CPU/global RSS/file-I/O and a further 12-run material trial observation passed; per-arm peak memory and broader evidence remain |
| M2 | Canonical section/reinforcement changes; separate full reference reanalysis; member quantities and common declared prices; rejected and unavailable candidates retained | terminal and explicit committed-state history screens implemented; real solver regressions and fixed-source 28 online/oracle history recoveries passed; prior four-row bundle consumed and exported by browser |
| M3 | Solver-produced paired samples; project/geometry/load-history isolation; train-only preprocessing; learned displacement proposals; held-out/OOD comparison and measured training/inference/recovery cost | entity-name invariant split preflight, collector/learning, in-range/OOD checks and full-study process costs verified locally; latest 12 evaluation runs passed; learned arm slower than secant; independently grouped corpus remains |
| M4 | Identical candidate-pool comparison of deterministic and learned selection; full-analysis count, total cost, missed-feasible/false-safe accounting and verified final candidates | member-position features and frozen training/report binding corrected; repeated two-pool terminal/history screens and combined oracle counts verified locally; saved measured producer bundles export without new analyses; repeated multi-family search, independent corpus and hosted integration remain |
| M5 | Workbench consumes and exports the verified candidate/model/result/quantity/price identities and performance differences | terminal/history values and limits displayed; all 8 actual history bundles passed parser and 16 desktop/mobile display/export checks; prior full standalone Workbench suite 148 passed |
| P1 | Broader public planar integration, CPU sparse parity and scale policy, independent OpenSees and second-solver verification | explicit strict extended sparse route implemented; unchanged 258-equation structural model passed dense parity and exact prefix restart after small-motion kinematic stabilization; legacy 256 cap retained; independent verification and broader scale acceptance remain |
| P2 | Material/3D/transient scope expansion with published and independent validation, exact job/review integration | bounded internal material/3D/transient paths already exist; actual fresh-process 3D restart/negative tests passed; public/job and independent validation gates remain |
| P3 | Extended shell/contact/cable/SSI/staged/distributed/GPU/design-code and public guarded-AI capabilities, after predecessor gates | planned; separately bounded implementation slices required |
| R1 | Current-main issue-state projection matches live GitHub state without weakening the live checks | local classifier/inventory fix and 52 tests passed; exact-main hosted check pending |
| R2 | Supplemental identity producer, consumer and production workflow integration with unchanged signature/receipt checks | open; existing PRs #432 and #434 are separate work |

Each implementation slice records its changed sources, focused tests and actual
measurements before being called complete. A code or fixture pass does not close
independent numerical verification, a license decision, hardware qualification,
human user observation, or release approval. A nonpositive measured speedup is
a valid experiment result. Construction estimates require an explicit price
scope; confirmed savings require the corresponding real takeoff/quote evidence.

External dependencies remain attributable to actual owners: dataset and software
license decisions (#290), licensed locked/blind corpus (#293), independent
platform/hardware/cross-code/user execution (#297), and administrator/reviewer
decisions on branch protection and full-suite trigger policy (#258/#260).

## Current slice

M1-M3 now share the physical case pipeline. The local empirical study uses one
synthetic serial-cantilever family and artificial split declarations to exercise
the integration. It is not an independent project, geometry-family or load-history
holdout. M4 priced browser integration is now verified locally; the issue-state
classifier still needs its exact-main hosted check. The
original dirty checkout and existing PR branches remain separate from this branch.

The no-price four-row producer bundle was generated from committed source
`9237a193354564860cef8efc356e38501f5be7e6`; its raw bytes were consumed by Chromium
and the downloaded manifest/report matched the originals. Material estimates and
selection remained unavailable. Browser checks used the repository's trusted
Node 24.20.0 runtime. This is local integration evidence, not deployed operation.

Actual section variations exposed two preexisting floating-point coordinate
binding errors: inverse rotation scaling need not return the original solver
coordinate bytes. The result adapter now binds original J5 solver bytes to the
exact forward-projected J3 physical state, and recovery replays those original
solver coordinates. Exact physical/material verification remains in place.
No convergence tolerance or generated protected receipt was changed.

Usage and scoped accounting are documented in `rc-fiber-design-experiments.md`.
The first measured learned-policy outcome is recorded in
`rc-fiber-learning-smoke-20260908.md`; it is not a positive acceleration result.

The preserved M4 learned and deterministic bundles from
`721448282d594f19fc4b2ce3158b369c579418dc` were consumed by the frontend built at
`848dc44b0d487aabc96719dd2f259b2c23d669eb`, without regeneration or additional
solver requests. Chromium selected `near_limit` and `baseline`, respectively;
quantity, estimate/reduction, response, limit status and downloaded report/manifest
JSON identities matched the producer. The synthetic KRW price table is not a quote
or confirmed saving. See `rc-fiber-priced-browser-smoke-20260908.md` for the
source hashes, export comparison semantics and unavailable auxiliary viewer data.

The later M5 review found that quantity and response differences existed in the
verified report but were not yet displayed. Commit `6e54814a3` exposes them without
requiring prices, and `6fa9154fb` wraps long comparison identities on narrow
screens. The two original priced bundles passed the updated consumer at
`6fa9154fbed1b8d6d791245de383f661c3967899`. Signed-delta, unavailable-baseline,
price-absent and mobile-panel regressions are included in 148 passing Workbench
tests. This panel check does not resolve the separate existing diagnostic-table
overflow of the full page.

A plain local full-pytest attempt collected 7,149 tests and stopped at the first
five failures: 256 passed, 3 skipped in 183.27 seconds. All five failures required
missing generated linear/modal-buckling case packages. The hosted workflow has
an explicit materialization stage, including protected evidence refresh, which
was not run in this implementation checkout. This is a failed unprepared local
attempt, not an exact-head full-suite pass. Hosted integration remains pending
human approval for push and Draft PR creation.

Commit `dd9950ebc` adds optional vector-increment backend timing and call/exception
counts without changing numerical solution payloads. Dense/sparse, singular,
reaction-only, unexpected-exception and recorder-clock tests passed, together with
stateful solver/benchmark tests (66), connected planar/recovery/suite/study tests
(86), and CI contracts (33). These are separate runs, not a full-suite claim.
At the fixed clean commit, both width cases passed all 8 measured reference/secant
runs and 4 reference episode checks. The backend scope includes matrix conversion
and sparse diagnostics, not isolated BLAS/LAPACK time. See
`rc-fiber-increment-runtime-20260908.md`. That increment-only observation did
not measure CPU, memory or I/O; the separate process follow-up below does. Earlier
learning studies retain their original source and resource limitations.

The fresh-process runtime wrapper now preserves a byte-bound suite and resource
sidecar, with separate workload/process CPU and input/report file-I/O scopes.
Linux memory uses post-exec `VmHWM`: a review probe reproduced parent-memory
contamination in `ru_maxrss`. Unsupported platforms retain unavailable memory.
Timeout, cancellation and damaged-sidecar paths preserve failure evidence without
crediting complete resource measurements. Frozen policy JSON is validated before
opt-in execution; it is not retrained. The final process/CI contract run passed
74 tests in 27.09 seconds. At fixed clean source `33216141d`, both two-step width
cases passed all 12 reference/secant/learned runs and 4 reference episode checks.
Suite CPU was 115.513504 seconds and process-local peak RSS was 104.859375 MiB.
The learned arm used four guard-accepted seeds and four OOD reference steps; it
was slower than secant in both cases. Input/report file-I/O measurements and
exact scopes are recorded in `rc-fiber-process-runtime-20260908.md`. That frozen-
policy observation excludes whole-study generation/training resources; the
follow-up below measures them. That original process run did not separate material
trial timing; the subsequent material observation below does for a bounded scope.
Per-strategy peak memory and independent hardware acceptance remain open.

The next M3 increment adds a full learning-study workload to the fresh-process
runner. It observes data collection, whole training attempts and frozen evaluation
with a single-use CPU/wall phase recorder outside study/numerical identities.
Skipped and failed phases keep their states and unavailable timing reasons.
Shared lifecycle/phase/CI regression passed 95 tests; the actual learning-process
integration and invalid inputs passed 7 tests; phase completeness/prefix checks
passed 11 tests. At fixed clean source `e0b169f5a`, four collection cases produced
eight samples; only four train samples fitted the frozen policy. All 12 evaluation
runs and four reference episode checks passed. CPU was 39.118291 s for collection,
0.001121 s for the whole training phase, and 117.324331 s for evaluation; whole
worker peak RSS was 105.933594 MiB. All eight learned evaluation steps accepted
guarded seeds, but learned end-to-end time was slower than secant in both cases.
See `rc-fiber-learning-process-runtime-20260908.md` for source/hash bindings,
resource scopes and the unavailable amortization counts.
Whole-worker RSS and bounded study I/O are supported; per-phase/per-strategy peak
memory, physical disk traffic, all-replay constitutive timing and independent
acceptance remain separate requirements.

A subsequent R1 source audit found no missing classifier implementation: the PR
workflow runs offline contracts, while live exact-main compares issue counts, IDs,
full projection and hashes. Live #438 remains open and this branch still has no
PR. An inventory retaining the pre-#438 projection would need reconciliation at
the actual integration/closure state; offline success cannot substitute for that
live check. No tracked inventory or protected evidence was refreshed. Read-only
remote checks still showed main `4de4e3f55aae1d267cf704cec7d7533f3a627498`,
PR #432 open/behind and #434 draft/open. Their integration and all external
approvals remain separate from this local implementation.

A further M1 increment separates steel/concrete material API intervals inside
attempted Newton/terminal/guard assembly. Numerical and checkpoint identities
remain unchanged; incomplete custom-section coverage keeps full totals unavailable.
The final scope passed 22 material tests, 52 neighboring tests, 75 stateful/runtime/
CI tests and 8 final instrumentation-failure tests in separate runs. At fixed clean
source `be8e5eef0`, all 12 two-width repeated runs and four
reference episode checks passed; every selected-step hash matched the earlier
frozen-policy observation. The declared assembly scope made 1,024 material calls
in 11.913080 ms, including guard work, with zero material
exceptions or timing errors. It excludes compilation/checkpoint/full-verification
replays and is a subset of inclusive assembly time. Both learned cases remained
slower than secant. See `rc-fiber-material-runtime-20260908.md` for source/artifact
bindings, runtime/resource observations and remaining independent/hosted gates.

M3/M4 review then reproduced three defects: entity aliases bypassed physical split
isolation, heterogeneous section placement collided in aggregate candidate features,
and detached training reports could bypass online training-model exclusion. Source
`33cf565ad` adds shared versioned name/order-invariant physical
identity, pre-solve cross-split rejection, 101 aggregate/member-position features
covering the existing 15-member bound, and frozen report/sample/policy membership
validation. Candidate report/policy/search schemas are v2; preserved old artifacts
are not rewritten or automatically retrained. Preflight cost is included in data
generation. Separate 73-test M3/CI, 49-test M4 and 1-test cost-scope groups passed.
At that fixed clean source, two heterogeneous placement models both passed full
reference/quantity verification. Their quantities match, while terminal translations
are 0.496429 and 0.413776 mm and the new member features distinguish them.
An all-entity renamed holdout duplicate was rejected
with zero analysis requests. See `rc-fiber-learning-identity-20260908.md`. This does
not supply the independent corpus, repeated multi-family/order-balanced search,
full-history limit envelopes or hosted integration still required by the roadmap.


M4 now has a declared multi-pool repeated suite with per-case balanced arm order,
all-input snapshots, fresh online/oracle requests, failure denominators and
artifact-deduplicated historical training costs. Synthetic suite contracts passed
57 tests, arm-order/binding regression 32 tests and CI ownership contracts 34 tests
in separate groups. At fixed clean source `412fda612`, two pools in one synthetic
family ran twice each: four ready comparisons, four training requests, 16 online
requests and 12 later oracle requests, total 32. The learned arm selected a fresh
verified feasible lower-fixture-cost candidate in every comparison; the
cost-ranked narrow candidate failed its terminal screen and deterministic retained
baseline. Pool A's paired time difference changed sign; pool B's learned arm was
slower in both repetitions. There is no consistent speedup. Generation/fit/suite
accounted wall was 306.098217 s. Pool A's 397-reuse arithmetic projection is
conditional, not demonstrated break-even. See `rc-fiber-candidate-suite-20260908.md`
for the exact protocol, raw hashes, timing dispersion and cost scopes. Independent
multi-family validation, full-history limit envelopes, per-strategy resources and
hosted integration remain open; the overall goal is not complete.

The next M2/M4 increment adds independently bound engineering recovery for every
positive committed static epoch, explicit history limits and preserved measured
producer exports. History failures retain verified terminal responses/quantities
without selection credit; terminal predictors do not gain history-safety authority.
Core history tests (10 plus one early-peak reducer), existing recovery tests (9),
history/design/search/suite integration (25) and final public/design/suite/CLI/CI
regression (137) passed in separate groups. At clean source `cc45b3449`, two pools
ran twice: four training plus 16 online plus 12 oracle requests, all 32 known.
All 28 online/oracle rows passed full reference and history recovery over epochs
1/2, and retained the earlier terminal-result/checkpoint hashes. Twenty repeated
rows passed both screens and eight narrow candidates failed. The learned arm
selected near-limit four times; deterministic retained baseline four times.
Both physical envelope maxima occur at epoch 2 in this low-load family; an earlier
physical peak is not demonstrated. Accounted generation/fit/suite wall was
343.863107 s; outer driver CPU was 344.006377 s. Learned was slower in pool A and
faster in pool B; the latter's 335-reuse projection is conditional and unobserved.
See `rc-fiber-committed-history-20260908.md` for protocol, source/raw hashes,
measurement scopes and browser results. Discrete committed-state recovery does
not close between-step/cyclic/dynamic extrema, independent material/family
verification, per-strategy resources or hosted/release requirements.
All eight actual v2 producer bundles subsequently passed the same-source parser
and Chromium desktop/mobile display and JSON-object export checks (16 viewport
observations, no additional analysis). TypeScript/Vite/viewer-delivery checks
passed without source changes. Auxiliary missing local evidence/sample/drawing
404s are retained; this remains comparison-panel integration evidence.

P1 now has an explicit `scipy_sparse_splu_cpu_exact_1536` choice with native CSR
Newton assembly and the existing strict condition/pivot/backward-error policy.
The old 256-equation default sparse scope and public topology limits remain.
The original 88-node/87-member/258-free-equation model first exposed common
dense/sparse small-motion cancellation. A numerically stable evaluation of the
same element kinematics, with unchanged physical tolerances and material laws,
then allowed both backends to converge at the original two load steps. All SI
rows matched at the existing comparison tolerance; prefix restart retained exact
physical checkpoint bytes and engineering recovery. The old backend still rejects
the same model before factorization. Metadata validation binds dimensions,
diagnostic counts/hashes/policy and reaction-only status consistently.
The complete new integration passed 25 tests; final metadata strengthening passed
five focused tests and one legacy public parity test. Separate kinematic (71),
Newton/diagnostic/configuration (59), neighboring public/stateful (58) and CI (34)
groups passed. See `planar-frame-extended-sparse-20260908.md` for failed attempts,
high-precision references, exact input/artifact hashes and execution counts.
The 1,536-equation diagonal fixture is algebraic evidence; final recovery still
uses dense matrices. Independent cross-code validation, larger structural-model
acceptance, end-to-end resource scaling and hosted/release requirements remain.
At fixed clean source `e2f6967ec`, one further actual planar CLI prefix-restart
request passed all public contracts. The full CLI JSON object matched the API
resumed result, and its physical checkpoint bytes/engineering rows matched the
uninterrupted extended result. Input/reference/source files and clean HEAD were
unchanged across execution. Raw hashes and request scope are recorded in the same
P1 document; no performance or independent external authority is inferred.
