# Structural Analysis

**Independent structural-analysis engine — Developer Preview**

This repository develops a Python structural-analysis engine around a strict separation of:

```text
user/model input
    → canonical model and execution topology
    → deterministic physics kernels and solver state
    → explicit result/recovery authority
    → evidence, replay, and AI observation layers
```

The project is not presented as a commercial-code replacement. Capabilities are promoted only when the exact model, state, solver, result, recovery, and verification contracts required for that claim are present.

## Current architecture

### 1. Canonical model and public analysis surface

- Detached canonical neutral-model loading and validation.
- Public linear-static, modal, linear-buckling, and model-health paths.
- A bounded public nonlinear two-bar truss Python API and CLI for the verified symmetric material-geometric Newton slice.
- A bounded public planar serial-cantilever RC fiber-frame API/CLI with exact
  checkpoint-prefix restart and J1--J5-backed engineering recovery.
- Safe output-path handling and fail-closed unsupported-feature reporting.

### 2. Engine v2 contracts

The backend-neutral contract layer includes:

- deterministic `ExecutionPlan`, equation scaling, sparse topology, and source commitments;
- immutable `StateIR` and vector artifacts;
- authoritative bounded linear numerical and engineering result contracts;
- `MaterialStateBundle` for ordered committed/trial constitutive-state transport;
- bounded nonlinear numerical-result and non-authoritative recovery-candidate contracts;
- `SolverEpisodeIR` for baseline, shadow, and guarded observation/replay episodes.

These contracts do not automatically make every solver path authoritative. Each application must bind its exact topology, state ancestry, terminal gates, and recovery operator.

### 3. Stateful nonlinear foundations

Current merged foundations include:

- stateful uniaxial steel and concrete-damage material paths;
- stateful axial chains with exact commit and rollback;
- RC axial-curvature fiber sections and stateful fiber-beam elements;
- bounded 2D stateful fiber-frame assembly, load stepping, persisted checkpoints, and complete checkpoint ancestry;
- checkpoint-to-`MaterialStateBundle` projection and complete material-state history;
- canonical six-DOF nonlinear fiber-frame topology and solver-coordinate scaling;
- physical force/moment equation scaling and residual traces;
- nonlinear kinematic-state history;
- combined kinematic/material execution-state binding;
- a J5 terminal receipt, bounded nonlinear numerical-result adapter, and exact
  recovery authority for reactions, member forces, section resultants, and
  fiber outputs in the supported source profile.

Those authority contracts do not generalize beyond their exact fixed-chord,
stateful RC source profile.

### 4. Reusable element kernels

- Two-node 2D corotational truss response with material and geometric tangent separation.
- Two-node planar corotational Euler–Bernoulli frame response with exact energy gradient and consistent Hessian.
- Stateful fiber-beam and axial-curvature section kernels.

Global corotational RC fiber-frame ownership, releases, rigid offsets, Timoshenko shear, and general 3D behavior remain future work.

### 5. AI control plane

The repository contains:

- `SolverEpisodeIR` for trace-bound solver observations and actions;
- a shadow-only step controller with policy/artifact/action identity binding, OOD checks, and deterministic baseline actions.

The real fiber-frame load path now records baseline and shadow
`SolverEpisodeIR` observations. Shadow proposals are not executed. No learned
policy, residual correction, Jacobian correction, material-law correction, or
design decision is authoritative.

### 6. Verification and evidence

- Deterministic analytic and bounded benchmark evidence remains separated from product claims.
- The two-element concrete-damage counter-example uses an explicit versioned imperfection to select a reproducible symmetric localization branch; mesh-objectivity and production claims remain false.
- The Lee-frame generator produces a non-promoting formal V&V candidate. Generated receipt bytes are not represented as publisher-source bytes, and formal credit remains blocked by source-use approval, independent reproduction, operator approval, and incomplete Level 2 evidence.

## Explicit non-claims

The current repository does **not** claim:

- general commercial nonlinear frame/shell capability;
- fiber-frame reaction, member-force, section, or fiber authority outside the
  exact bounded recovery profile;
- mesh-objective concrete fracture;
- general contact, cable, shell, diaphragm, release, or rigid-offset support;
- production sparse/HIP parity for the nonlinear fiber-frame path;
- design-code compliance or automatic engineering approval;
- guarded or autonomous AI solver control;
- formal commercial verification hierarchy closure.

## Immediate product critical path

```text
merged topology/scaling/state binding and SolverEpisode adapter
    → merged nonlinear terminal, ResultIR, and exact recovery
    → merged bounded public RC fiber-frame API/CLI
    → broader corotational and sparse-backend coverage
    → formal Level 2/3 verification evidence
```

## Development

```bash
python -m pip install -e .[dev]
python -m pytest -q
```

Bounded public nonlinear two-bar example:

```bash
python -m structural_analysis.api.nonlinear_truss_cli model.json \
  --out result.json \
  --report-out report.json
```

Bounded public RC fiber-frame example:

```bash
python -m structural_analysis.api.nonlinear_fiber_frame_cli \
  examples/public_rc_fiber_frame_cantilever.json \
  --load-steps 4 \
  --out rc-result.json \
  --report-out rc-report.json \
  --checkpoint-out rc-checkpoint-chain.json
```

Generated readiness and evidence artifacts are source-derived. Do not hand-edit them or infer a broader claim from a passing bounded benchmark.
