# AI design exploration implementation register

Started 2026-09-08 from main `4de4e3f55aae1d267cf704cec7d7533f3a627498`.
The owner requested sustained implementation of the agreed roadmap. This file
tracks development work, not product readiness or external verification credit.
The product objective remains in `ai-nonlinear-cost-workbench-plan.md`.

| ID | Deliverable and acceptance | State |
| --- | --- | --- |
| M1 | Multiple supported physical cases; reference/secant/optional learned arms; repeated timing, dispersion, full history/recovery and failure coverage; immutable experiment identity and separate timing | suite implemented; local 18-run full-history/recovery study passed; scope and negative acceleration result recorded |
| M2 | Canonical section/reinforcement changes; separate full reference reanalysis; member quantities and common declared prices; rejected and unavailable candidates retained | implementation and real solver regressions passed; actual four-row bundle consumed and exported by browser |
| M3 | Solver-produced paired samples; project/geometry/load-history isolation; train-only preprocessing; learned displacement proposals; held-out/OOD comparison and measured training/inference/recovery cost | collector/learning, local in-range study and frozen-policy actual OOD rejection passed; learned arm slower than secant; independently grouped corpus remains |
| M4 | Identical candidate-pool comparison of deterministic and learned selection; full-analysis count, total cost, missed-feasible/false-safe accounting and verified final candidates | bounded learner/search and actual 5-candidate tests passed; M2 result accessor implemented; priced browser integration pending |
| M5 | Workbench consumes and exports the verified candidate/model/result/quantity/price identities and performance differences | actual Python producer to Chromium and JSON export verified; 40 focused browser contracts passed |
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
holdout. M4 and the issue-state classifier are the next integration work. The
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
