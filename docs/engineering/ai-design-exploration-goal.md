# AI design exploration implementation register

Started 2026-09-08 from main `4de4e3f55aae1d267cf704cec7d7533f3a627498`.
The owner requested sustained implementation of the agreed roadmap. This file
tracks development work, not product readiness or external verification credit.
The product objective remains in `ai-nonlinear-cost-workbench-plan.md`.

| ID | Deliverable and acceptance | State |
| --- | --- | --- |
| M1 | Multiple supported physical cases; reference/secant/optional learned arms; repeated timing, dispersion, full history/recovery and failure coverage; immutable experiment identity and separate timing | suite, increment timing and fresh-process CPU/RSS/file-I/O wrapper implemented; 18-run learned study, 8-run increment observation and new 12-run CPU/RSS/file-I/O observation passed; whole-study CPU/global RSS/file-I/O also observed; per-arm peak memory and broader evidence remain |
| M2 | Canonical section/reinforcement changes; separate full reference reanalysis; member quantities and common declared prices; rejected and unavailable candidates retained | implementation and real solver regressions passed; actual four-row bundle consumed and exported by browser |
| M3 | Solver-produced paired samples; project/geometry/load-history isolation; train-only preprocessing; learned displacement proposals; held-out/OOD comparison and measured training/inference/recovery cost | collector/learning, in-range/OOD checks and full-study process costs observed; latest 12 evaluation runs passed; learned arm slower than secant; independently grouped corpus remains |
| M4 | Identical candidate-pool comparison of deterministic and learned selection; full-analysis count, total cost, missed-feasible/false-safe accounting and verified final candidates | bounded learner/search and actual 5-candidate tests passed; both preserved priced bundles consumed and exported by Chromium; independent corpus and hosted integration remain |
| M5 | Workbench consumes and exports the verified candidate/model/result/quantity/price identities and performance differences | verified quantity/response deltas now displayed; actual priced bundles rechecked including mobile panel containment and export; full standalone Workbench suite 148 passed |
| P1 | Broader public planar integration, CPU sparse parity and scale policy, independent OpenSees and second-solver verification | public wrapper parity/restart/256-equation scope checks passed; nested-result authority validation fixed; broader scale and independent verification remain |
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
follow-up below measures them. Per-strategy peak memory, material-only update
timing and independent hardware acceptance remain open.

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
memory, physical disk traffic, material-only timing and independent acceptance
remain separate requirements.

A subsequent R1 source audit found no missing classifier implementation: the PR
workflow runs offline contracts, while live exact-main compares issue counts, IDs,
full projection and hashes. Live #438 remains open and this branch still has no
PR. An inventory retaining the pre-#438 projection would need reconciliation at
the actual integration/closure state; offline success cannot substitute for that
live check. No tracked inventory or protected evidence was refreshed. Read-only
remote checks still showed main `4de4e3f55aae1d267cf704cec7d7533f3a627498`,
PR #432 open/behind and #434 draft/open. Their integration and all external
approvals remain separate from this local implementation.
