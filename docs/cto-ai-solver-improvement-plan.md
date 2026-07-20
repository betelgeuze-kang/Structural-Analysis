# CTO plan: authoritative nonlinear solver and AI control plane

## Product objective

Build an independent structural-analysis program whose deterministic physics engine remains the source of numerical truth while AI assists only through observable, bounded, reversible control actions.

```text
AI proposes
deterministic guards decide
physics solver executes
result/recovery contracts authorize
evidence determines promotable scope
```

## Completed foundation

### Contract and state plane

- Engine v2 execution, scaling, state, vector, numerical-result, and engineering-result contracts.
- Ordered `MaterialStateBundle` lifecycle with imported-manifest hardening.
- Nonlinear numerical-result terminal gates and a non-authoritative recovery candidate.
- `SolverEpisodeIR` with trace-bound terminal state, baseline/shadow/guarded rules, and data-use receipts.

### Fiber-frame vertical foundation

- Stateful RC fiber section and beam kernels.
- Bounded 2D fiber-frame assembly and Newton load stepping.
- Persisted checkpoints and epoch-zero-rooted checkpoint ancestry.
- Complete checkpoint-to-material-state projection.
- Canonical six-DOF nonlinear topology and solver-coordinate scaling.
- Physical force/moment equation scaling and residual trace.
- Nonlinear kinematic-state history.
- Combined kinematic/material execution-state binding.
- Bounded J5 nonlinear terminal convergence receipt with exact Newton replay.
- Real baseline/shadow fiber-frame SolverEpisode adapter with exact rollback.
- J5-backed fiber-frame `NonlinearNumericalResultIR` adapter with bounded
  convergence, committed-displacement, and committed-material-state authority.
- Exact terminal fiber-frame engineering recovery with bounded reaction,
  member-force, section-resultant, and fiber-output authority.

### Reusable geometric-nonlinear kernels

- Corotational 2D truss.
- Corotational planar Euler–Bernoulli frame.

### Product and evidence seeds

- Bounded public nonlinear two-bar truss API/CLI.
- Deterministic concrete-damage localization evidence with explicit branch-selection imperfection.
- Non-promoting Lee-frame formal V&V candidate generator.
- Shadow-only deterministic solver-step controller.

## Implemented first-wave slice

### A. Real fiber-frame SolverEpisode adapter — implemented

**Goal:** convert the existing accepted fiber-frame load path into replayable baseline and shadow episodes.

Minimum first slice:

- one observation for the initial checkpoint and each accepted load step;
- combined execution-state hash, checkpoint hash, topology hash, scaling hash, residual metrics, accepted/rollback disposition, and load factor;
- deterministic baseline next-step action;
- shadow proposal recorded but never executed;
- no raw customer model or constituent-state bytes in the episode;
- training eligibility false unless explicit license/privacy receipts are attached.

Acceptance:

- same solve produces the same episode manifest and hash;
- terminal state equals the last accepted execution-state observation;
- rollback cannot mutate the accepted state;
- policy/artifact/action hashes replay exactly;
- episode authority remains false.

The implementation additionally requires the exact J5 receipt for every ready
path, supports a terminal one-step exact rollback path, binds every source step
and physical residual trace by canonical hash, and keeps runtime at zero under
an explicit no-timing-authority profile.

## Implemented second-wave slice

### B. J5-backed fiber-frame NonlinearNumericalResultIR adapter — implemented

**Goal:** consume the existing J5 terminal receipt and grant bounded
numerical-state authority only after the remaining ResultIR bindings pass.

Required bindings:

- exact combined execution-state hash;
- load-path/checkpoint-chain hash;
- final physical and scaled residual traces;
- increment and acceptance tolerances;
- fallback and regularization counts;
- boundary-condition receipt;
- backend receipt;
- terminal displacement artifact.

Initial authority scope:

```text
convergence                 eligible
committed displacement      eligible
committed material state    eligible
reactions/member forces     not yet authoritative
design/code results         not authoritative
```

The implementation preserves the explicit decision not to emit `StateIR v1`,
replays the complete J1--J5 source chain, emits strict reduced-system,
full-residual, boundary-condition, and backend receipts, and binds immutable
terminal canonical six-DOF displacement bytes. Generic engineering recovery
remains fail-closed for this source profile; the exact source-specific operator
below is the separate authority-promotion path.

## Implemented third-wave slice

### C. Exact engineering recovery operator — implemented

**Goal:** independently replay engineering outputs from exact committed state rather than trusting solver-returned arrays.

Required replay:

- geometry and local/global transformations;
- section and integration-point order;
- committed constituent-state bytes;
- section integration and member end forces;
- element-to-global scatter;
- free-equation equilibrium;
- constrained reaction partition;
- energy and local/global consistency receipts.

Only this operator may promote bounded reaction, member-force, section, and fiber-output authority.

The implementation restarts from the terminal parent checkpoint and terminal
J3 coordinates, reruns the constitutive transition, recomputes section
resultants from ordered fiber stresses, integrates member end forces, performs
local/global transformation and global scatter, and partitions reactions only
on authored fixed equations. It requires exact checkpoint and material-bundle
constituent bytes plus bounded equilibrium, transformation, work, and energy
consistency gates. Manifests remain descriptor-only, and the promoted result
retains explicit exclusions for design, code, release, commercial, general
topology, and geometric-nonlinear authority.

## Implemented fourth-wave slice

### D. Bounded public RC fiber-frame slice — implemented

Initial supported profile:

- XY plane, `UX/UY/RZ` active in canonical six-DOF node space;
- small-displacement fixed-chord formulation;
- explicit rectangular RC fiber sections;
- supported steel and concrete material profiles;
- zero prescribed displacement and proportional nodal loading;
- dense CPU reference Newton;
- checkpoint restart and exact fail-closed compiler.

Keep releases, offsets, diaphragms, distributed loads, arc length, general topology, and design checks outside the first profile.

The first public compiler further narrows topology to one connected,
unbranched serial cantilever chain with a single fully fixed endpoint. It
requires explicit material and section parameters, bounded model sizes, exact
row fields, and a proportional nodal-load pattern. Ready results traverse the
complete J1--J5 source chain and exact recovery operator. Persisted restart
chains must be exact configured load-path prefixes and are fully replayed
before continuation. The Python result can export any accepted prefix, while
the CLI can read and write canonical checkpoint-chain artifacts without
aliasing model, restart, result, or report paths.

## Next implementation wave

### E. Corotational stateful fiber frame

Sequence:

```text
corotational elastic frame kernel [implemented]
    → basic-deformation protocol [implemented]
    → stateful axial-curvature section [implemented independently]
    → corotational fiber-beam [implemented element boundary]
    → global assembly [implemented dense kernel boundary]
    → consistent Newton and load control [next]
    → adaptive stepping and arc length
```

The extracted stateless boundary publishes the three current-chord basic
deformations, their exact first and second global derivatives, and generic
material/geometric tangent recovery from a structural basic force/tangent
response. The elastic kernel consumes this boundary without changing its
result contract. It deliberately retains the principal `atan2` chord-angle
branch; multi-turn unwrapping requires committed state and is supplied only by
the stateful corotational consumer. See
`docs/corotational-frame2d-basic-kinematics.md`.

The axial-curvature section and its Gauss-point fiber beam are now connected to
the corotational basic modes through an immutable element state. The element
tracks a committed chord-angle branch, maps section forces/tangents back to
the basic system, and recovers exact global material plus geometric tangents.
Its focused boundary covers sequential multi-turn rigid motion, same-parent
nonlinear tangent checks, cyclic RC state evolution, deterministic replay, and
rollback-safe unchanged-parent trials. See
`docs/stateful-corotational-fiber-beam2d.md`.

The additive corotational frame assembly now gathers/scatters those exact member
responses across shared `[ux, uy, theta]` DOFs, retains separate material and
geometric global tangents, applies the existing length-valued rotation scaling,
and validates hash-addressed frame checkpoints against exact member displacement
bytes. Its focused boundary covers shared-node accumulation, a same-parent
nonlinear global Jacobian finite difference, sequential multi-turn rigid motion
for every member, deterministic replay, and unchanged-parent trial branching.
See `docs/stateful-corotational-fiber-frame2d-global-assembly.md`.

Solver-owned positive-epoch acceptance, consistent Newton/line search, adaptive
load control, arc length, checkpoint-chain persistence, external member
validation, and G1 closure remain open.

Required tests include finite rigid rotation, energy-gradient and tangent checks, P-Delta portal response, cyclic RC members, restart/replay, and snap-through paths.

### F. Production CPU sparse baseline

```text
deterministic CSR/BSR topology
    → sparse assembly
    → CPU sparse direct oracle
    → CPU FGMRES
    → reviewed preconditioners
    → dense/sparse/iterative parity
```

GPU/HIP acceleration must reuse the same operator and result contracts and must never become the only truth backend.

### G. Formal verification closure

Priority order:

1. Level 2 OpenSees comparison with exact material/path mapping.
2. A second independent solver or implementation.
3. Clean-runner, source/version, license, and artifact receipts.
4. Level 3 published benchmark attachment.
5. Contiguous hierarchy promotion only after all lower levels pass.

## AI rollout policy

### Phase 1 — baseline episodes

Record deterministic solver behavior without AI proposals.

### Phase 2 — shadow

Allow proposals for next step size only. Execute the deterministic baseline action and evaluate proposal quality offline.

### Phase 3 — guarded

A proposed step may execute only when:

- model family is supported;
- OOD is false;
- uncertainty passes threshold;
- proposal/action identity matches;
- a deterministic guard receipt is present;
- residual behavior remains acceptable;
- exact rollback and deterministic fallback are available.

### Prohibited until separate reviewed contracts

- residual or response correction;
- Jacobian/tangent correction;
- constitutive-law correction;
- result correction;
- design-code or engineering approval decisions.

## Data governance

- Do not embed raw customer models in episodes.
- Split train/evaluation data by model family, not by near-duplicate run.
- Preserve failed and rollback episodes.
- Default training eligibility to false.
- Require explicit license and privacy receipts.
- Bind policy version and artifact hash to every proposal.

## Definition of commercial-readiness progress

Commercial readiness is not a single passing benchmark. A promotable capability needs:

- a stable public input profile;
- deterministic compile and execution contracts;
- exact committed-state and result authority;
- independent recovery for engineering outputs;
- restart and replay;
- bounded failure behavior;
- formal verification evidence with permitted sources;
- documented support and excluded-feature boundaries.

Until those conditions are satisfied for a capability, keep it labeled Developer Preview, candidate, diagnostic, or non-authoritative as appropriate.
