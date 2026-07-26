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

Unified nonlinear frame API with the exact one-bay corotational portal candidate:

```bash
python -m structural_analysis.api.nonlinear_frame_cli \
  examples/public_corotational_rc_portal.json \
  --profile corotational_one_bay_portal.v1 \
  --load-steps 4 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --out portal-result.json \
  --report-out portal-report.json \
  --checkpoint-out portal-checkpoint-chain.json
```

The portal path supports dense or native COO/CSR Newton tangent assembly, returns
exact local contract results and an epoch-zero checkpoint chain, and binds each sparse
solve to an unregularized SuperLU/COLAMD factorization and exact conditioning receipt.
It remains a bounded candidate until both independent Level 2 slots and the remaining
promotion gates pass; production-scale conditioning remains a later gate.

Connected branching Frame2D candidate with proportional prescribed support values:

```bash
python -m structural_analysis.api.nonlinear_frame_cli \
  examples/public_corotational_branching_frame.json \
  --profile corotational_connected_frame2d.v1 \
  --load-steps 4 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --out connected-result.json \
  --report-out connected-report.json \
  --checkpoint-out connected-checkpoint-chain.json
```

This profile is bounded to a connected planar graph with 2–128 nodes and 1–256
non-parallel members. Releases, rigid offsets, distributed member loads, direct
displacement control, external Level 2 evidence, and release promotion remain
separate gates.

Generated readiness and evidence artifacts are source-derived. Do not hand-edit them or infer a broader claim from a passing bounded benchmark.

<!-- BEGIN GENERATED CAPABILITY SUPPORT -->
## Generated capability support matrix

This table is generated from artifacts/manifests/capabilities.yaml. Do not edit it directly.

| Capability | Status | Public | Authority | Interfaces | Exact profile / boundary |
| --- | --- | --- | --- | --- | --- |
| Neutral canonical model | supported | yes | validated_input_contract | python_api, cli | structural-analysis-canonical-model.v1; Only schema-declared entities and units are accepted. |
| MIDAS MGT import | bounded_public | yes | input_translation_with_provenance | python_api, cli | topology_and_supported_property_subset; Unsupported records remain explicit; exact native round-trip is not closed. |
| IFC model-health import | bounded_public | yes | entity_scan_and_model_health_only | python_api, cli | ifc_step_model_health; Not a general analysis-ready IFC structural-model compiler. |
| Linear static analysis | bounded_public | yes | numerical_and_engineering_within_supported_elements | python_api, cli, workbench | cpu_dense_or_scipy_sparse_supported_frame_truss; No general shell, contact, staged-construction, or design-code authority. |
| Whole-model modal analysis | bounded_public | yes | numerical_within_explicit_frame_truss_mass_profile | python_api, cli | dense_symmetric_generalized_eigen_v1; The public default is dense and no independent Level 2 comparison is promoted. |
| Whole-model linear buckling | bounded_public | yes | numerical_within_explicit_preload_profile | python_api, cli | dense_symmetric_generalized_eigen_v1; The public default is dense and no independent Level 2 comparison is promoted. |
| Nonlinear two-bar truss | bounded_public | yes | bounded_material_geometric_newton | python_api, cli | symmetric_two_bar_material_geometric_v1; The profile does not generalize to arbitrary truss or frame topology. |
| Fixed-chord RC fiber frame | bounded_public | yes | exact_reaction_member_section_fiber_recovery | python_api, cli | planar_serial_cantilever_explicit_rectangular_rc.v1; Serial cantilever only; zero prescribed movement; dense CPU load control. |
| ResultIR SI quantity and tolerance catalog | bounded_public | yes | comparison_contract_only_no_result_promotion | python_api, json_schema | hashed_si_quantity_catalog_and_absolute_plus_relative_linf_v1; Defines fixed SI units and comparison tolerances only; it cannot create solver authority or make corotational output public. |
| Corotational 2D fiber frame | experimental | no | bounded_j1_j5_and_exact_engineering_recovery_candidate | python_api, cli | corotational_connected_frame2d.v1; Connected planar 2-128-node, 1-256-non-parallel-member load-control CPU dense or native COO/CSR candidate with branching, support UX/UY/RZ subsets, proportional nodal loads, and proportional prescribed displacement; disconnected graphs, parallel members, releases, rigid offsets, distributed loads, direct displacement control, production-scale conditioning, both independent Level 2 comparisons, and release promotion remain open. |
| Native sparse nonlinear backend | experimental | no | bounded_native_coo_csr_and_fail_closed_exact_conditioning_candidate | python_api, cli, internal_python | corotational_element_triplet_coalesce_sorted_csr_fp64_plus_blocked_exact_1536.v1; The public exact-conditioning path remains bounded to 256 equations. A separate CPU-only blocked exact diagnostic is bounded to 1536 equations and is integrated only into the bounded experimental 3D graph candidate. Exact inverse-column conditioning has quadratic work and does not close production-scale policy, performance or memory evidence, external V&V, or release promotion. |
| OpenSees Level 2 verification | blocked | no | none | evidence | independent_operator_promotion_required; Fresh pinned technical comparisons and a same-operator container-isolated replay pass narrowly, including an elastic-state public corotational portal path, but independent operator attestation, legal review, material-nonlinear breadth, and a Level 2 promotion receipt are absent. |
| Second independent solver Level 2 verification | blocked | no | none | evidence | independent_operator_promotion_required; Fresh pinned CalculiX comparisons pass narrowly, but independent operator attestation, legal review, broader coverage, and a second-solver Level 2 promotion receipt are absent. |
| Fracture-energy concrete | experimental | no | bounded_source_bound_uniaxial_crack_band_candidate | internal_python, evidence | localized_crack_band_rc_tie_2_4_8_meshes.v1; Source-bound mesh-objectivity evidence is limited to a seeded single-crack uniaxial RC tie. Arbitrary frame or shell localization, multiaxial concrete, confinement, bond slip, published or external validation, independent engineering review, and release promotion remain open. |
| Cyclic corotational fiber-frame benchmarks | experimental | no | bounded_repository_benchmark_candidate | internal_python, evidence | two_member_planar_material_state_commit_rollback.v1; Repository-generated steel, concrete, composite, and link cases only; no published cyclic acceptance, 3D response, or release authority. |
| Workbench result and evidence review | bounded_public | yes | consumer_only | workbench | typed_workbench_case_and_evidence_reader; Workbench display and review decisions never create solver truth. |
| AI solver shadow control | shadow_only | no | proposal_and_evaluation_only | internal_python, evidence | deterministic_baseline_plus_replay_bound_offline_scorecard.v1; Shadow proposals are not executed and cannot alter solver truth. |
| Guarded AI execution | blocked | no | none | internal_python | offline_counterfactual_and_guard_receipts_required; No production action execution or autonomous engineering authority. |
| ROCm/HIP production backend | blocked | no | none | hardware_runner | performance_track_after_cpu_sparse_and_external_vv; Residency, full-path parity, fallback, and hardware provenance gates remain open. |
<!-- END GENERATED CAPABILITY SUPPORT -->
