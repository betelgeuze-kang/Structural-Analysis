# Local-free G1 closure contract and runbook

Purpose: define the G1 closure contract that can be prepared without local solver execution, GPU/HIP runtime, or protected evidence refresh.

This packet is **non-promoting**. It does not create a full-load checkpoint, close G1, prove ROCm/HIP residency, or promote an independent solver claim.

## Current G1 position

Known current state:

- Direct residual terminal gate: ready
- Full-load HIP/Newton lane: not ready
- Active terminal requirement: `full_load_checkpoint_1p0`
- Terminal requirements: `0/4`
- Observed load scale: `0.656`
- Required load scale: `1.0`
- Recommended next direction: `consistent_residual_jacobian_newton_rocm_worker`
- Row-only correction loop: stopped
- Support/link row gap: disfavored

A separate CPU diagnostic now reaches `lambda=1.0` from zero for the current
state-invariant linear reference-geometry adapter and replays a serialized
`lambda=0.75` checkpoint byte-for-byte. It is deliberately not counted in the
terminal requirements: it is not a `mgt-direct-residual-newton-state.v1` state,
the raw `*MATERIAL` table leaves 79 frame bindings unresolved, and the available
exact type/name `*DGN-MATL` aliases remain engineer-review-required. A separate
actual-adapter diagnostic now connects the finite-chord axial correction to the
physical residual and an analytic current-state tangent action; centered
difference and component-force summation are retained only as independent
audits, while the solve residual and tangent share the same reference/load-delta/
finite-chord parents. That residual definition is bound to canonical hash
`sha256:2da9d3377eaf3cd9b196e82535c3a3593502079652306bc5705e13d910cca62f`,
which each dependent receipt builder recomputes independently. A bounded local CPU
matrix-free diagnostic uses cancellation-stable finite-chord formulas, accepts
two descending full Newton corrections, and leaves an in-memory residual of
`1.1767242540372536e-6 N`. A separate load-controlled path accepts semantic `LIVE`
factors `0.25/0.5/0.75/1.0`, ends at `0.0004447424730642524 N`, restarts exactly
from `0.5`, and exercises exact rollback with a one-correction-limited probe. An
adaptive one-correction controller additionally rejects two actual large steps,
restores the accepted checkpoint, halves the step, reaches `1.0` through
`0.5/0.75/1.0`, and restarts exactly from `0.5`. A three-scale perturbation audit
around the direct full-load state measures local directional Newton order
`1.99998507` to `1.99998515`. All 20 tangent solves across the fixed, restart,
direct, rollback, adaptive, and local-quadratic probes bind the same free-DOF,
residual-formula, reference-load, current-tangent, and fixed-preconditioner
identities. Their host recurrence uses the ordered Python-`fsum` arithmetic
profile. The tangent formula and 12 immutable parent arrays are contract-bound,
while NumPy evaluation order and SuperLU output remain outside the cross-platform
determinism claim. The
local `0.0005 N` gate now passes for this narrow axial diagnostic, but it still
does not establish a complete frame/shell/material tangent, material state,
arc-length branch, an authoritative G1 checkpoint, or a production HIP path.

Authoritative artifacts:

- `implementation/phase1/release_evidence/productization/mgt_g1_direct_residual_terminal_gate_report.json`
- `implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json`
- `implementation/phase1/release_evidence/productization/g1_consistent_newton_full_load_checkpoint_candidate_runner.json`
- `implementation/phase1/release_evidence/productization/g1_f2g_f2h_cause_narrowing_status.json`
- `implementation/phase1/release_evidence/productization/g1_load_dependent_near_null_geometric_stiffness_comparison.json`
- `implementation/phase1/release_evidence/productization/g1_mgt_state_updated_frame_axial_geometry_preflight.json`
- `implementation/phase1/release_evidence/productization/g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.json`
- `implementation/phase1/release_evidence/productization/g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.json`
- `implementation/phase1/release_evidence/productization/g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt.json`

## Governing residual contract

All G1 engines should share one physical residual:

```text
R(u, lambda, s) = F_internal(u, s) - lambda * F_external
```

The Newton tangent must be the derivative of the same residual:

```text
J(u, lambda, s) = dR / du
```

Do not promote:

- fixed-point map residual as physical residual;
- regularized residual as direct residual;
- row-only correction as full nonlinear equilibrium;
- sub-full-load checkpoint as full-load readiness;
- a full-load linear-reference diagnostic as a nonlinear G1 checkpoint;
- CPU diagnostic fallback as production HIP proof.

## Required G1 terminal closure gates

### Gate 1 — Full-load 1.0 checkpoint

Required evidence:

- loadable `mgt-direct-residual-newton-state.v1` checkpoint;
- `load_scale >= 1.0`;
- no load-path provenance contradiction;
- direct residual and increment gates pass at full load;
- checkpoint can be reloaded and replayed.

### Gate 2 — Full-mesh nonlinear equilibrium

Required evidence:

- full frame/shell/boundary graph is active;
- nonlinear equilibrium is not a partial component solve;
- fallback-zero or fallback trace is explicit;
- direct residual is evaluated from the physical residual;
- residual and increment gates pass without hidden regularization promotion.

### Gate 3 — Material Newton breadth

Required evidence:

- state-updated material Newton path is active;
- frame and shell material tangent are evaluated at the same state as the residual;
- material state is persisted in checkpoint/replay;
- bounded tangent smoke is not promoted as path-dependent material closure;
- material tangent JVP checks pass where applicable.

### Gate 4 — Production ROCm/HIP residual/JVP residency

Required evidence:

- ROCm runtime available;
- `/dev/kfd` and `/dev/dri` available to validation user;
- no CPU fallback counted as HIP proof;
- production HIP residual/Jacobian path true;
- HIP batch replay for current tangent residual rows;
- matrix-free global Krylov uses HIP solver;
- JVP rows retained;
- accepted-state tangent refresh uses HIP, not CPU.

## Recommended execution sequence

1. Repair or provision ROCm/HIP runtime.
2. Refresh HIP consistency proof for current HEAD.
3. Build consistent residual/Jacobian Newton full-load candidate generator.
4. Generate full-load 1.0 checkpoint candidate.
5. Run full-load child direct probe with HIP refresh.
6. Verify material Newton breadth and fallback-zero gates.
7. Rerun `g1_full_load_hip_newton_lane_report.json` with `--fail-blocked`.
8. Rerun product readiness snapshot in check mode.

## Minimum JVP check

For any G1 tangent promotion, require:

```text
J(u) v ~= [R(u + eps v) - R(u - eps v)] / (2 eps)
```

The comparison must use the same residual path and the same active model state.

## Closure acceptance criteria

G1 is closed only when:

- `full_load_gate_passed=true`;
- `full_mesh_nonlinear_equilibrium_closed=true`;
- `material_newton_breadth_closed=true`;
- `production_rocm_hip_residency_closed=true`;
- direct residual and increment pass at full load;
- CPU/HIP parity or HIP-resident proof is attached;
- product readiness snapshot no longer reports G1 numerical blockers.

## Claim boundary

Allowed current claim:

> G1 has a ready direct-residual terminal slice and strong cause narrowing, but full-load/full-mesh/material/HIP closure remains open.

Forbidden current claim:

- G1 closed
- full-load 1.0 solved
- full nonlinear full-mesh equilibrium ready
- production HIP solver truth ready
- material Newton breadth closed
- independent commercial solver ready
