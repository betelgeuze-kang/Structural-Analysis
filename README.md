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

The bounded 2D corotational RC fiber-frame path now owns global dense/sparse
assembly, RZ end releases, finite-rotation rigid offsets, and uniform
initial-local-axis dead loads. Timoshenko shear and general 3D behavior remain
separate future scopes.

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
- general contact, cable, shell, diaphragm, or release/offset behavior beyond the
  bounded planar RZ/global-XY member-feature contract;
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

The accepted repository boundaries and ordered P0-P3 implementation plan are in
[Repository Architecture and Product Development Roadmap](docs/repository-architecture-and-product-roadmap.md).
The [roadmap closure matrix](docs/product-roadmap-closure-matrix.md) records the
current evidence state without promoting partial, proxy, or externally blocked
work.

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

Unified nonlinear frame API with the corotational portal candidate:

```bash
python -m structural_analysis.api.nonlinear_frame_cli \
  examples/public_corotational_rc_portal.json \
  --profile corotational_one_bay_portal.v1 \
  --load-steps 4 \
  --out portal-result.json \
  --report-out portal-report.json \
  --checkpoint-out portal-checkpoint-chain.json
```

Connected branching frame with multiple supports and a prescribed displacement:

```bash
python -m structural_analysis.api.nonlinear_frame_cli \
  examples/public_corotational_branching_frame.json \
  --profile corotational_connected_frame2d.v1 \
  --load-steps 4 \
  --residual-tolerance 1e-9 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --out branching-result.json \
  --report-out branching-report.json \
  --checkpoint-out branching-checkpoint-chain.json
```

Member releases, rigid offsets, and a uniform distributed dead load:

```bash
python -m structural_analysis.api.nonlinear_frame_cli \
  examples/public_corotational_member_features.json \
  --profile corotational_connected_frame2d.v1 \
  --load-steps 4 \
  --residual-tolerance 1e-9 \
  --out member-features-result.json \
  --report-out member-features-report.json \
  --checkpoint-out member-features-checkpoint-chain.json
```

The same connected-frame endpoint supports direct single-DOF displacement control;
the terminal load factor is solved rather than assumed to be one:

```bash
python -m structural_analysis.api.nonlinear_frame_cli \
  examples/public_corotational_member_features.json \
  --profile corotational_connected_frame2d.v1 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --control-mode displacement_control \
  --control-node N2 \
  --control-dof UY \
  --terminal-control-displacement -0.00016 \
  --out displacement-result.json \
  --report-out displacement-report.json \
  --checkpoint-out displacement-checkpoint-chain.json
```

The endpoint returns exact local contract results, but the corotational profile is
not a release claim until both independent Level 2 slots and the remaining promotion
gates pass.

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
| Whole-model modal analysis | bounded_public | yes | numerical_within_explicit_frame_truss_mass_profile | python_api, cli | dense_symmetric_generalized_eigen_v1; The public default is dense; the opt-in sparse extractor is experimental, still uses dense whole-model assembly, and has no independent Level 2 comparison. |
| Whole-model linear buckling | bounded_public | yes | numerical_within_explicit_preload_profile | python_api, cli | dense_symmetric_generalized_eigen_v1; The public default is dense; the opt-in sparse reciprocal extractor is experimental, still uses dense whole-model assembly, and has no independent Level 2 comparison. |
| Nonlinear two-bar truss | bounded_public | yes | bounded_material_geometric_newton | python_api, cli | symmetric_two_bar_material_geometric_v1; The profile does not generalize to arbitrary truss or frame topology. |
| Fixed-chord RC fiber frame | bounded_public | yes | exact_reaction_member_section_fiber_recovery | python_api, cli | planar_serial_cantilever_explicit_rectangular_rc.v1; Serial cantilever only; zero prescribed movement; dense CPU load control. |
| Corotational 2D fiber frame | experimental | no | bounded_j1_j5_and_exact_engineering_recovery_candidate | python_api, cli | corotational_one_bay_portal.v1; Load control and direct single-DOF displacement control, RZ end releases, global-XY rigid offsets, and uniform initial-local-axis dead loads are bound; both Level 2 slots and release promotion remain open. |
| Native sparse nonlinear backend | experimental | no | bounded_native_coo_csr_and_fail_closed_exact_conditioning_candidate | python_api, cli, internal_python | corotational_element_triplet_coalesce_sorted_csr_fp64_plus_blocked_exact_1536.v1; The public exact-conditioning path remains bounded to 256 equations. A separate CPU-only blockwise exact diagnostic is bounded to 1536 equations and is wired only into the experimental stateful 3D graph path; an actual 258-free-equation frame passes. Its exact inverse-column diagnostic still has quadratic work and does not close production-scale policy, performance/memory evidence, external V&V, or release promotion. |
| Sparse modal and buckling extraction | experimental | no | bounded_sparse_low_mode_extraction_candidate | python_api, cli, internal_python | arpack_modal_and_superlu_reciprocal_buckling.v1; Whole-model assembly remains dense; binary mode artifacts, production-scale conditioning, independent Level 2 V&V, and release promotion are open. |
| Nonlinear transient SDOF reference | experimental | no | bounded_algorithm_and_checkpoint_candidate | internal_python | newmark_average_acceleration_bilinear_sdof.v1; One force-driven DOF only; no frame assembly, base excitation, adaptive stepping, published validation, or release authority. |
| Connected corotational 2D fiber frame | experimental | no | bounded_exact_engineering_candidate | python_api, cli | corotational_connected_frame2d.v1; Connected simple graph only; load control or direct single-DOF displacement control is supported; prescribed support histories remain proportional to solved load factor; member loads are uniform initial-local-axis dead loads; both Level 2 slots remain open. |
| OpenSees Level 2 verification | blocked | no | none | evidence | clean_runner_required; Fresh pinned OpenSees technical executions and a read-only-source/network-disabled same-operator container reproduction pass narrow modal, consistent-mass modal/MAC, linear-static, and fixed two-element elastic spatial-frame comparisons, but independent operator attestation, public corotational nonlinear breadth, Level 2 normalization, review, and promotion receipt are absent. |
| Second independent solver Level 2 verification | blocked | no | none | evidence | independent_clean_runner_required; Fresh pinned CalculiX technical executions and a read-only-source/network-disabled same-operator container reproduction pass narrow axial-member and whole-model repeated-mode linear-buckling/subspace comparisons, but independent operator attestation, broader frame/nonlinear coverage, review, and a promoted second-solver Level 2 package are absent. |
| Fracture-energy concrete | experimental | no | bounded_uniaxial_crack_band_mesh_objectivity_candidate | internal_python | localized_crack_band_rc_tie_2_4_8_meshes.v1; Mesh-objectivity evidence remains limited to the seeded single-crack uniaxial RC tie. The same law is accepted by the experimental 3D member axial adapter, but arbitrary frame/shell localization, multiaxial concrete, confinement, bond slip, published validation, and release promotion remain open. |
| Uniaxial confined concrete | experimental | no | bounded_material_point_and_axial_member_checkpoint_candidate | internal_python | mander_uniaxial_monotonic_compression.v1; The native-sparse 3D adapter adds immutable current/max-compression lineage but no unloading law. Cyclic confined-concrete behavior, distributed fibers, multiaxial response, localization, published calibration, and design authority remain open. |
| Cyclic bond-slip connector | experimental | no | bounded_material_point_single_mode_and_distributed_two_layer_member_candidate | internal_python | piecewise_softening_cyclic_connector.v1; The 3D axial adapter statically condenses one connector coordinate; a separate two-layer fiber member integrates cyclic connector points at two/three Gauss stations and condenses a linear two-node slip field. General anchorage, shear lag, uplift/contact, connector groups, published cyclic validation, and design authority remain open. |
| Partial composite interaction material point | experimental | no | bounded_material_point_single_mode_axial_and_distributed_two_layer_fiber_member_candidate | internal_python | axial_two_layer_discrete_connector.v1; One axial adapter condenses a single slip coordinate. The separate distributed candidate couples two axial-biaxial fiber layers to a linear two-node slip field and connector quadrature, but it is not a general shear-lag/uplift/contact, effective-width, connector-group, published validation, production-scale, or design-authority formulation. |
| Stateful axial-biaxial fiber section | experimental | no | bounded_same_parent_section_and_distributed_member_candidate | internal_python | plane_section_axial_biaxial_discrete_fibers.v1; Two/three-point 3D member integration is verified with numerical basic-mode derivatives. A separate two-layer member adds condensed connector quadrature; shear/torsion material coupling, general shear lag/uplift/contact, cyclic confinement, multiaxial concrete, production-scale material behavior, published validation, and design authority remain open. |
| Corotational 3D frame | experimental | no | bounded_dense_elastic_native_sparse_distributed_biaxial_fiber_and_partial_composite_verification_candidate | internal_python | dense_elastic_native_sparse_axial_distributed_biaxial_fiber_and_partial_composite_corotational_timoshenko_frame3d.v1; The dense elastic reference remains bounded to 16 nodes, 32 members, and 60 free equations. The separate native-sparse graph is bounded to 128 nodes, 256 members, and 768 free equations; a 44-node/43-member, 258-free-equation solve is verified with blocked exact conditioning. Native COO/CSR, six axial constitutive contracts, a two/three-point axial-biaxial fiber correction, and a two-layer member with connector quadrature and a condensed linear slip field verify reversal, commit/rollback, exact checkpoint resume, rigid-motion objectivity, and same-parent tangents. Shear/torsion remain elastic and the 3D basic-mode mappings use disclosed numerical derivatives. The fixed two-element same-operator OpenSees comparison covers only the dense elastic branch. General shear lag/uplift/contact, cyclic confined concrete, connector groups, member features, warping coupling, analytic and production-scale sparse/material 3D behavior, multi-turn rotation, independent external review, committed-current-HEAD promotion, and release authority remain open. |
| Shear-deformable 3D frame element | experimental | no | bounded_local_stiffness_candidate | internal_python | two_node_timoshenko_frame3d_shear_condensed.v1; Linear prismatic local element only; effective shear areas must be explicit and nonlinear/global integration is open. |
| Vlasov torsion and warping kernel | experimental | no | bounded_local_energy_candidate | internal_python | vlasov_hermite_twist_gradient_2node.v1; Separate four-DOF linear kernel; not assembled into the 12-DOF frame and no open-section stress or external validation authority. |
| Explicit member initial-imperfection mesh | experimental | no | geometry_generation_only | internal_python | sinusoidal_member_bow_local_yz.v1; One-member half-sine geometry only; no code amplitude, eigenmode scaling, residual stress, nonlinear solve, or design authority. |
| Cyclic corotational fiber-frame benchmarks | experimental | no | bounded_repository_benchmark_candidate | internal_python, evidence | two_member_planar_material_state_commit_rollback.v1; Repository-generated steel, concrete, perfect-bond composite, and link cases only; no published cyclic acceptance, confinement/bond-slip member integration, 3D response, or release authority. |
| Published Lee-frame snap-through candidate | experimental | no | bounded_numerical_comparison_without_hierarchy_credit | internal_python, evidence | fixed_20_element_elastic_lee_frame_table11.v1; The fixed Lee-frame numerical decision passes, but publisher-source bytes, source-use approval, independent clean-runner reproduction, formal operator approval, completed Level 2 prerequisites, and Level 3 hierarchy credit are absent. |
| Shell and plate elements | blocked | no | none | none | p3_after_p0_p2_entry_gate; No canonical-core public shell or plate formulation; phase1 shell assets are proxy, research, or technical evidence only. |
| Structural contact | blocked | no | none | none | p3_after_p0_p2_entry_gate; No canonical-core public contact element, search, enforcement, state, or externally validated solver profile. |
| Cable elements | blocked | no | none | none | p3_after_p0_p2_entry_gate; No canonical-core public cable formulation, prestress/sag state, nonlinear solve integration, or external validation. |
| Soil-structure interaction | blocked | no | none | none | p3_after_p0_p2_entry_gate; Phase1 SSI research assets do not establish a promoted canonical-core solver profile, external V&V, or design authority. |
| Staged construction | blocked | no | none | none | p3_after_p0_p2_entry_gate; No promoted activation/deactivation, state-transfer, load-history, checkpoint, and external-validation contract in canonical core. |
| Mixed frame-shell nonlinear analysis | blocked | no | none | none | p3_after_p0_p2_entry_gate; The two-DOF named seed and large sparse technical probe do not provide a general shell element or mixed nonlinear product solve. |
| Distributed execution | blocked | no | none | none | p3_after_single_host_job_service_promotion; The durable job-service candidate is single-host; no consensus, remote replication, multi-host scheduling, identity, or SLO evidence exists. |
| Three validated customer-shadow cases | blocked | no | none | evidence | completed_project_customer_retained_metadata_minimum_3; The validated completed-project customer-shadow count is 0/3; templates and intake packets do not count as evidence. |
| Structural design-code modules | blocked | no | none | none | p3_after_p0_p2_entry_gate; Optimization scripts and KDS input data are not an implemented, versioned, reviewed, externally validated design-code authority module. |
| Workbench result and evidence review | bounded_public | yes | consumer_only | workbench | typed_workbench_case_and_evidence_reader; Workbench display and review decisions never create solver truth. |
| Job service checkpoint and resume | experimental | no | orchestration_and_integrity_only | internal_python, http_adapter, worker, workbench | sqlite_wal_content_addressed_single_host_exact_resume.v1; Single-host candidate only; distributed consensus, production identity/TLS/SLO evidence, remote replication, and release promotion remain open. |
| Signed engineering-review package | blocked | no | none | evidence | current_head_prerequisites_trusted_reviewer_ed25519.v1; The deterministic review-material and detached-signature verifier are implemented, but the trusted reviewer registry is empty, the current candidate is not a clean current HEAD, prerequisite Level 2/3 and deployment evidence is missing, and no reviewer assertion or signature is attached. |
| AI solver shadow control | shadow_only | no | proposal_and_evaluation_only | internal_python, evidence | deterministic_baseline_plus_replay_bound_offline_scorecard.v1; Shadow proposals are not executed and cannot alter solver truth. |
| Guarded AI execution | blocked | no | none | internal_python | offline_counterfactual_and_guard_receipts_required; No production action execution or autonomous engineering authority. |
| ROCm/HIP production backend | blocked | no | none | hardware_runner | performance_track_after_cpu_sparse_and_external_vv; Residency, full-path parity, fallback, and hardware provenance gates remain open. |
<!-- END GENERATED CAPABILITY SUPPORT -->
