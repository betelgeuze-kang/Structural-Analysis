# AI design exploration implementation register

Started 2026-09-08 from main `4de4e3f55aae1d267cf704cec7d7533f3a627498`.
The owner requested sustained implementation of the agreed roadmap. This file
tracks development work, not product readiness or external verification credit.
The product objective remains in `ai-nonlinear-cost-workbench-plan.md`.

| ID | Deliverable and acceptance | State |
| --- | --- | --- |
| M1 | Multiple supported physical cases; reference/secant/optional learned arms; repeated timing, dispersion, full history/recovery and failure coverage; immutable experiment identity and separate timing | suite implemented and focused tests passed; measured study pending |
| M2 | Canonical section/reinforcement changes; separate full reference reanalysis; member quantities and common declared prices; rejected and unavailable candidates retained | implementation and real solver regressions passed; bundle integration pending |
| M3 | Solver-produced paired samples; project/geometry/load-history isolation; train-only preprocessing; learned displacement proposals; held-out/OOD comparison and measured training/inference/recovery cost | collector/learning implemented and tested; held-out runtime study pending |
| M4 | Identical candidate-pool comparison of deterministic and learned selection; full-analysis count, total cost, missed-feasible/false-safe accounting and verified final candidates | planned |
| M5 | Workbench consumes and exports the verified candidate/model/result/quantity/price identities and performance differences | implemented; browser contracts passed; real producer bundle check pending |
| P1 | Broader public planar integration, CPU sparse parity and scale policy, independent OpenSees and second-solver verification | planned; independent verification required |
| P2 | Material/3D/transient scope expansion with published and independent validation, exact job/review integration | planned; external inputs required |
| P3 | Extended shell/contact/cable/SSI/staged/distributed/GPU/design-code and public guarded-AI capabilities, after predecessor gates | planned; separately bounded implementation slices required |
| R1 | Current-main issue-state projection matches live GitHub state without weakening the live checks | open |
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

M1 and M2 are the immediate integration target. M3's learning contract can be
implemented independently, but its empirical evaluation requires solver-produced
samples from the completed model/case pipeline. The original dirty checkout and
existing PR branches remain separate from this development branch.

Actual section variations exposed two preexisting floating-point coordinate
binding errors: inverse rotation scaling need not return the original solver
coordinate bytes. The result adapter now binds original J5 solver bytes to the
exact forward-projected J3 physical state, and recovery replays those original
solver coordinates. Exact physical/material verification remains in place.
No convergence tolerance or generated protected receipt was changed.

Usage and scoped accounting are documented in `rc-fiber-design-experiments.md`.
