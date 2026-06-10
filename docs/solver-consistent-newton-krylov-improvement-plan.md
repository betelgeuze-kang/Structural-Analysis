# Solver-Consistent Newton/Krylov Improvement Plan

Status: active implementation reference.

This document captures the current improvement direction for closing the remaining
commercial structural solver gaps. It is intentionally stricter than a residual
correction roadmap: heuristic or AI-assisted residual correction may propose
directions, seeds, or coarse spaces, but product promotion must happen only through
the physical solver gates.

## Current Open Gap Focus

The commercial ledger remains open with `16/20` requirements closed. The active
non-external gaps are:

- `G1` Full 3D Global FEA Core: partial.
- `G7` Korean Medium/Large Real-Project Corpus: partial and operator/source dependent.
- `G9` Runtime, GPU, Performance, And Scale: partial.
- `G6` V&V and external benchmarks: external blocked.

The next locally closable work should prioritize `G1` and `G9`.

## Principle

Residual correction is not a standalone closure engine. The correct architecture is:

1. Define the physical residual `R(u, lambda) = F_int(u) - lambda F_ext`.
2. Assemble or approximate residual-consistent Jacobian action using frame geometric
   stiffness, material tangent, shell/surface tangent, authored supports, and finite
   springs under the same residual contract.
3. Use AI, row-active FD-JVP, secant, and element-block corrections only as candidate
   direction, initial-state, or coarse-basis generators.
4. Promote only when regularization-free direct residual replay, increment gate,
   boundary-condition/energy gates, and the appropriate production backend gate pass.

This prevents residual-only improvement from being mistaken for commercial solver
closure.

## G1 Priority: Adaptive Preconditioned Global Newton/Krylov

The strongest current G1 route is the current-tangent right-preconditioned global
residual-JVP Krylov path with adaptive tangent regularization and signed/globalized
alpha search.

Measured evidence:

- Plain alpha8 continuation saturated at `6931.557151848129 N`; the next same-operator
  run recorded `no_residual_descent`.
- Widening the same GMRES basis from `3` to `6` vectors worsened the candidate.
- Tangent regularization factor `1e-7` moved the durable frontier to
  `6931.541434355825 N`, but a same-factor replay was sub-floor.
- Factor `3e-7` from that frontier improved but remained sub-floor.
- Factor `1e-6` promoted `6931.50857647534 N`.
- Same-factor checkpoint continuation then promoted:
  - `6931.50857647534 -> 6931.46276643071 N`
  - `6931.46276643071 -> 6931.432267962403 N`
  - `6931.432267962403 -> 6931.422474165393 N`
- The next `1e-6` follow-up hit `no_residual_descent`, and `3e-6` from the same
  frontier also worsened.

Therefore the next implementation target is an adaptive controller, not another
manual single-factor smoke. It should:

- Resume from the latest promoted checkpoint.
- Evaluate a configured tangent-regularization ladder.
- Use signed alpha and trust/arc-length compatible alpha candidates.
- Promote only if the direct residual improvement passes the governance floor and
  the increment gate.
- Stop and record a boundary when all configured factors fail or worsen.
- Keep CPU-diagnostic receipts separate from official ROCm/HIP product closure.

## G1 Candidate Generators: Seed Only

The following paths are useful as proposal mechanisms but not as closure engines:

- row-active current-tangent residual correction
- finite-difference residual-row JVP correction
- secant-family candidate generation
- compact element-block correction
- older orthogonal-projection or distributed-node residual correction

These should feed Newton/Krylov as seeds, preconditioner hints, or coarse-basis
candidates. They must not directly promote a final result unless the physical
direct-residual replay, increment gate, boundary-condition/energy gates, and
backend governance gates pass.

## G9 Priority: Backend-Quality Preconditioner, Not Post-Polishing

G9 is a GPU sparse solver and preconditioner quality gap. Local residual polishing
and one-level corrections are heavily tested and mostly counter-evidence.

Known direction:

- Stay on the AMD ROCm/HIP lane.
- Target full CSR replay on the full 6DOF coupled operator.
- Improve translation/rotation block Schur quality.
- Use connected graph/domain decomposition and interface coarse operators.
- Connect energy-minimizing or GENEO-style modes to a real multilevel hierarchy,
  not merely a single low-rank correction.
- Keep memory-fault-prone post-Schur hooks opt-in and non-promoting.

Known counter-evidence includes signed Schur basis, aggregate count tuning,
RHS-hotspot partitioning, simple overlap, post-interface polish, pair smoothing,
ILU0/IC/Jacobi variants, and same-subspace reconditioning.

## Do Not Promote

The following are explicitly non-closing:

- fixed-point residual success without the increment/remap gate
- residual-only candidates with failed increment gate
- CPU diagnostic results as commercial closure evidence
- local row/patch/FD column widening as final proof
- default-enabling post-Schur polishing after memory faults
- AI surrogate or residual model updates that alter final results without solver gates

## Immediate Implementation Queue

1. Add an adaptive preconditioned global Newton/Krylov controller around the existing
   global residual-JVP path. Initial implementation exists in
   `run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`.
2. Record controller receipts with factor rows, alpha rows, promotion checkpoints,
   and boundary reasons.
3. Use row/FD/secant/element-block evidence only as optional seed/coarse-basis input.
4. For G9, stop simple post-polish work and move to Schur/DD or multilevel
   preconditioner backend quality.
5. Keep all commercial ledger rows honest until residual, increment, backend, and
   external evidence gates are actually closed.

Latest controller smoke:

- Receipt: `mgt_direct_residual_adaptive_preconditioned_global_newton_smoke.json`.
- Start checkpoint: `6931.422474165393 N`.
- Factor ladder: `[1e-6, 3e-6]`.
- Promotions: `0`.
- Stop reason: `no_regularization_factor_promoted`.
- Rows reproduce the measured boundary: `1e-6` best worsens to
  `6931.433329472165 N`, and `3e-6` best worsens to `6931.477813298451 N`.

This is not closure, but it moves the process from manual single-factor probing to
a documented controller receipt with boundary detection.

Latest seed-enabled controller smoke:

- Receipt: `mgt_direct_residual_adaptive_preconditioned_global_newton_secant_seed_smoke.json`.
- Start checkpoint: `6931.422474165393 N`.
- Seed: secant-family candidate generation with windows `[4, 8, 16, 32]`.
- Factor ladder: `[1e-6, 3e-6]`.
- Promotions: `1`.
- Final residual: `6931.387293436975 N`.
- Accepted components: secant-family seed and matrix-free global Krylov.

This confirms the intended architecture: old residual-correction history is useful
when demoted to a seed generator and then replayed through the direct residual
Krylov controller.

Continuation evidence:

- Receipt: `mgt_direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_smoke.json`.
- Start checkpoint: `6931.387293436975 N`.
- Final residual: `6931.346282307703 N`.
- Promotions: `1`.
- Accepted components: secant-family seed and matrix-free global Krylov.
- Runtime: about `650 s` for the one-step CPU-diagnostic controller.

The route is repeatable, but runtime is already high enough that the controller
needs budget controls before broader sweeps.

Budget-control update:

- Receipt: `mgt_direct_residual_adaptive_preconditioned_global_newton_runtime_budget_smoke.json`.
- New CLI: `--max-controller-runtime-seconds`.
- Behavior: the in-process child probe is allowed to finish once launched, but the
  controller checks the budget before launching each child and after each child
  returns.
- Smoke result: with a zero-second budget, the controller records
  `runtime_budget_exceeded=true`, starts no child rows, and promotes no checkpoint.

This keeps "run until closed" compatible with governance: future G1 continuation
can be extended in budgeted slices, with every launch boundary and timeout decision
visible in receipts instead of hidden in ad hoc terminal runs.

Budgeted continuation evidence:

- Receipt: `mgt_direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_2_smoke.json`.
- Start checkpoint: `6931.346282307703 N`.
- Runtime budget: `720 s`; actual runtime: about `670 s`.
- Final residual: `6931.331952798518 N`.
- Promotions: `1`.
- Accepted components: matrix-free global Krylov accepted; secant-family seed was
  enabled but not accepted in this step.

This keeps the controller route alive, but the improvement is tapering. The next
material implementation should either alter the global residual/Jacobian operator
or move the same controller concept toward the ROCm/HIP production lane.
