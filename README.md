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

Global corotational Frame3D, stateful fiber Frame3D, finite rigid offsets, RZ
releases, uniform member dead loads, and bounded direct displacement control now
exist as non-public candidate implementations. Their representability,
execution, numerical/recovery authority, external V&V, and release eligibility
are reported independently in the generated v2 capability matrix below;
implementation is not a public-support claim.

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
non-parallel members. Finite rigid offset, RZ end release, uniform member dead
load, and internal direct displacement control implementations are recorded as
separate non-public candidate rows. General member-feature coverage, unified
direct-control exposure, external Level 2 evidence, and release promotion
remain separate gates.

Generated readiness and evidence artifacts are source-derived. Do not hand-edit them or infer a broader claim from a passing bounded benchmark.

## Readiness source of truth

- Canonical product readiness snapshot: status `stale_or_inconsistent`, blocker_count `112`, paid_pilot_ready=`false`, release_ready=`false`. Canonical blocker categories: numerical `8`, benchmark `5`, software product `83`, future commercial `16`. The authoritative artifact is `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`; inspect it without changing protected evidence with `python3 scripts/build_product_readiness_snapshot.py --json --no-write`.
- Open Benchmark Developer Preview readiness: `implementation/phase1/release_evidence/productization/developer_preview_readiness.json` and `implementation/phase1/release_evidence/productization/developer_preview_readiness.md` report developer_preview_ready=`false`, blocker_count `85`, and future_commercial_blocker_count `27`. Developer Preview blockers are numerical `11`, benchmark `2`, and software product `72`. The included scope is public/open benchmark import, deterministic analysis/reporting, benchmark scorecard review, and a local GUI review workflow.
- Developer Preview excludes permit automation, structural engineer replacement, multi-tenant SaaS/account/license server operation, and independent AI/GNN/surrogate truth claims. The customer shadow, license approval, commercial SLA, 30-run CI streak, and external approval receipt remain Commercial Release evidence rather than Developer Preview claims. The new feature freeze `frozen_until_developer_preview_baseline_is_clean`, AI training freeze `frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed`, and GPU/HIP track `performance_track_after_cpu_reference_parity` keep AI/GNN/surrogate truth behind the deterministic reference solver, residual/Jacobian/Newton closure, and benchmark truth.
- Developer Preview RC status: `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json` and `implementation/phase1/release_evidence/productization/developer_preview_rc_status.md` report status `blocked`, deliverables `10/10`, and final gates `5/9`. The remaining boundary keeps selected medium models, silent import loss zero, Linux/Windows reproducibility, and human new-user workflow observation open; clean-clone and large crash/OOM-free execution are ready. This does not close full Phase 3, G1 full nonlinear full-mesh/material Newton, Linux/Windows parity, or the human new-user workflow observation.
- The canonical PM blocker register reports release areas `4/16`, open blocker handoff `63`, release-area blockers `42`, external input-required blockers `10`, and local remediation-ready blockers `53`. These are handoff counts, not release promotion.
- `python3 scripts/report_release_evidence_freshness.py` currently reports `1/14` passing receipts, including the tracked `developer_preview_rc_status.json` surface. Missing or stale receipts keep Developer Preview RC final gates and Commercial Release claims blocked.
- Release-mode checks use `python3 scripts/check_github_actions_self_hosted_runner_status.py --check --fail-blocked` and `python3 scripts/build_product_readiness_snapshot.py --check` without rewriting tracked evidence. A runner query failure remains a blocker; `--write-query-error-evidence` is an explicit diagnostic write.

<!-- BEGIN GENERATED CAPABILITY SUPPORT -->
## Generated capability support matrix

This table is generated from the v2 registry at `artifacts/manifests/capabilities.yaml`. Do not edit it directly. `implemented` and `executable` do not mean `public`; numerical, recovery, external-V&V, and release authority remain independent.

| Capability | Status | Representable | Implemented | Executable | Public | Numerical authority | Recovery authority | External V&V | Release eligible | Exact profile / boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| Neutral canonical model | supported | yes | yes | yes | yes | validated_input_contract | not_applicable | 0 | no | structural-analysis-canonical-model.v1; Only schema-declared entities and units are accepted. |
| MIDAS MGT import | bounded_public | yes | yes | yes | yes | input_translation_with_provenance | not_applicable | 0 | no | topology_and_supported_property_subset; Unsupported records remain explicit; exact native round-trip is not closed. |
| IFC model-health import | bounded_public | yes | yes | yes | yes | entity_scan_and_model_health_only | not_applicable | 0 | no | ifc_step_model_health; Not a general analysis-ready IFC structural-model compiler. |
| Linear static analysis | bounded_public | yes | yes | yes | yes | numerical_and_engineering_within_supported_elements | numerical_and_engineering_within_supported_elements | 0 | no | cpu_dense_or_scipy_sparse_supported_frame_truss; Dense and sparse solves use the same source-bound 6DOF force/moment row and rotation-column scaling; scaling inputs reject coercive or value-losing conversion to real binary64, and exact scaled condition numbers are emitted only through 256 free equations and remain explicitly unavailable above that bound. |
| Whole-model modal analysis | bounded_public | yes | yes | yes | yes | numerical_within_explicit_frame_truss_mass_profile | numerical_within_explicit_frame_truss_mass_profile | 0 | no | dense_symmetric_generalized_eigen_v1; The reduced stiffness and mass matrices use source-bound 6DOF symmetric coordinate scaling before eigen extraction; physical mode vectors are recovered and rechecked against the original matrices. |
| Whole-model linear buckling | bounded_public | yes | yes | yes | yes | numerical_within_explicit_preload_profile | numerical_within_explicit_preload_profile | 0 | no | dense_symmetric_generalized_eigen_v1; The reduced elastic and geometric stiffness matrices use source-bound 6DOF symmetric coordinate scaling before eigen extraction; physical buckling vectors are recovered and rechecked against the original matrices. |
| Nonlinear two-bar truss | bounded_public | yes | yes | yes | yes | bounded_material_geometric_newton | bounded_material_geometric_newton | 0 | no | symmetric_two_bar_material_geometric_v1; The profile does not generalize to arbitrary truss or frame topology. |
| Fixed-chord RC fiber frame | bounded_public | yes | yes | yes | yes | exact_reaction_member_section_fiber_recovery | exact_reaction_member_section_fiber_recovery | 0 | no | planar_serial_cantilever_explicit_rectangular_rc.v1; Serial cantilever only; zero prescribed movement; dense CPU load control. |
| ResultIR SI quantity and tolerance catalog | bounded_public | yes | yes | yes | yes | comparison_contract_only_no_result_promotion | comparison_contract_only | 0 | no | hashed_si_quantity_catalog_and_absolute_plus_relative_linf_v1; Defines fixed SI units and comparison tolerances only; it cannot create solver authority or make corotational output public. |
| Planar frame verified alpha | bounded_public | yes | yes | yes | yes | exact_bounded_candidate | exact_bounded_candidate | 0 | no | planar_frame_verified_alpha.v1; This Developer Preview row promotes only the source-bound nonlinear load-control path; the wider linear-static, modal, and linear-buckling product profile remains to be unified behind this API. |
| Corotational 2D fiber frame | experimental | yes | yes | yes | no | bounded_j1_j5_and_exact_engineering_recovery_candidate | bounded_j1_j5_and_exact_engineering_recovery_candidate | 0 | no | corotational_connected_frame2d.v1; Connected planar load-control remains experimental and non-public. ModelIR v2 profile bounded_planar_frame_alpha represents the exact nonlinear materials, rectangular RC fiber sections, six-DOF constraints, planar member features, and one nonlinear load pattern; its typed adapter binds source content/semantic/provenance hashes through a typed bounded nonlinear ExecutionPlan receipt, EquationScaling, topology, and unified engineering result. The ExecutionPlan receipt grants source-bound topology and DOF-ordering identity only; convergence and numerical-result authority remain separate. The unified entry executes bounded finite rigid offsets, RZ end releases, and initial-local uniform member dead loads with exact bounded engineering-recovery authority; blocked results expose a schema-enforced stable reason_code plus detailed kind/path/detail. The nonlinear ExecutionPlan remains distinct from linear-static Engine v2 ExecutionPlan v1. A source-bound Ubuntu/Windows and Python 3.10/3.12 exact result/checkpoint/recovery replay gate now enters through the public ModelIR v2 adapter for both the member-feature and prescribed-settlement fixtures and binds each fixture's content, semantic, provenance, adapter, execution-plan, result, checkpoint, and recovery hashes; no retained passing current-source four-way platform matrix receipt is attached yet. Fresh checksum-bound current-source host receipts record actual same-operator OpenSees/CalculiX execution for the exact cantilever, member-feature, prescribed-settlement, column-buckling, reaction, and member-recovery rows. The retained clean-runner summary has mismatched host/container source and metric sets, so same_operator_execution_binding is unavailable and supplies no current container-parity credit. The separate main-only GitHub provenance workflow still has no retained run attestation, so current_source_execution_attached=false remains for that workflow only. Independent operator attestation and Level 2 promotion remain absent, so external_vv_level stays 0. Direct displacement control remains lower-level only. Prescribed-only iterative paths with free equations and no force reference fail closed until a source-bound kinematic reference-force scaling contract exists. No other member-feature family, design, or release authority is created. |
| Native sparse nonlinear backend | experimental | yes | yes | yes | no | bounded_native_coo_csr_and_fail_closed_exact_conditioning_candidate | not_applicable | 0 | no | corotational_element_triplet_coalesce_sorted_csr_fp64_plus_blocked_exact_1536.v1; The public exact-conditioning path remains bounded to 256 equations. A separate CPU-only blocked exact diagnostic is bounded to 1536 equations and is integrated only into the bounded experimental 3D graph candidate. Exact inverse-column conditioning has quadratic work and does not close production-scale policy, performance or memory evidence, external V&V, or release promotion. |
| OpenSees Level 2 verification | blocked | yes | yes | yes | no | none | not_applicable | 0 | no | independent_operator_promotion_gate_v1; Pinned external comparison values remain available, and current-product replay passes for all 25 bounded recommendation rows. Nine core rows retain their prior replay-only receipts. The sixteen-row supplemental receipt now preserves the historical model, runner, result-schema, and package bytes, validates the retained self-hashed OpenSees/CalculiX results against those execution inputs, and compares them with product results regenerated from the current source. No external runtime was executed while generating the current receipts, so all 25 rows are explicitly replay-only: 25/25 technical references, 0/25 fresh current-source technical rows, 0 technically missing rows, and 0/25 promotion-eligible rows. This completes only the bounded technical-reference inventory; fresh external reruns, cross-environment parity, independent operator identity, project legal approvals, complete scientific decisions, and a signed promotion decision remain absent. The Level 2 gate remains blocked, external_vv_level stays 0, and no design, commercial-equivalence, or release authority is granted. |
| Second independent solver Level 2 verification | blocked | yes | no | no | no | none | not_applicable | 0 | no | independent_operator_promotion_required; Fresh checksum-bound current-source host receipts record actual same-operator CalculiX execution. The retained local clean-runner summary has mismatched host/container source and metric sets, so it is unavailable for current container-parity credit. No retained GitHub workflow attestation, independent operator attestation, legal review, broader coverage, or second-solver Level 2 promotion receipt is attached. |
| Fracture-energy concrete | experimental | yes | yes | yes | no | bounded_source_bound_uniaxial_crack_band_candidate | bounded_source_bound_uniaxial_crack_band_candidate | 0 | no | localized_crack_band_rc_tie_2_4_8_meshes.v1; Source-bound mesh-objectivity evidence is limited to a seeded single-crack uniaxial RC tie. Arbitrary frame or shell localization, multiaxial concrete, confinement, bond slip, published or external validation, independent engineering review, and release promotion remain open. |
| Cyclic corotational fiber-frame benchmarks | experimental | yes | yes | yes | no | bounded_repository_benchmark_candidate | bounded_repository_benchmark_candidate | 0 | no | two_member_planar_material_state_commit_rollback.v1; Repository-generated steel, concrete, composite, and link cases only; no published cyclic acceptance, 3D response, or release authority. |
| Workbench result and evidence review | bounded_public | yes | yes | yes | yes | consumer_only | not_applicable | 0 | no | typed_workbench_case_evidence_and_result_ir_reader; Durable-job publication is accepted only when raw artifact hashes, the complete typed corotational engineering ResultIR shape and descriptor bundle, unified-result bindings, authority axes, and the exact core validation report all agree; legacy normalized result rows are not exposed by the durable reader. |
| AI solver shadow control | shadow_only | yes | yes | yes | no | proposal_and_evaluation_only | not_applicable | 0 | no | deterministic_baseline_plus_replay_bound_offline_scorecard.v1; Shadow proposals are not executed and cannot alter solver truth. |
| Guarded AI execution | blocked | yes | no | no | no | none | not_applicable | 0 | no | offline_counterfactual_and_guard_receipts_required; No production action execution or autonomous engineering authority. |
| ROCm/HIP production backend | blocked | yes | no | no | no | none | not_applicable | 0 | no | performance_track_after_cpu_sparse_and_external_vv; Residency, full-path parity, fallback, and hardware provenance gates remain open. |
| Frame2D finite rigid offset | experimental | yes | yes | yes | no | bounded_candidate | exact_bounded_candidate | 0 | no | connected_planar_frame2d_finite_rigid_offset_candidate.v1; Bounded connected planar Frame2D candidate only. |
| Frame2D RZ end release | experimental | yes | yes | yes | no | bounded_candidate | exact_bounded_candidate | 0 | no | connected_planar_frame2d_rz_end_release_candidate.v1; RZ-only bounded release with same-parent local equilibrium and Schur condensation. |
| Frame2D uniform member dead load | experimental | yes | yes | yes | no | bounded_candidate | exact_bounded_candidate | 0 | no | connected_planar_frame2d_uniform_dead_load_candidate.v1; Uniform dead load in the initial member-local axis only. |
| Frame2D prescribed support displacement | experimental | yes | yes | yes | no | bounded_candidate | exact_bounded_candidate | 0 | no | bounded_planar_frame2d_proportional_prescribed_support_candidate.v1; Constrained UX, UY, or RZ terminal values are proportional to the load factor; this is distinct from direct displacement control of a free DOF. |
| Frame2D direct displacement control | experimental | yes | yes | yes | no | bounded_candidate | source_authenticated_checkpoint_replay_candidate | 0 | no | single_control_dof_dense_augmented_newton_candidate.v1; Internal dense augmented-Newton path with one free UX/UY control DOF. |
| Global corotational Frame3D | experimental | yes | yes | yes | no | bounded_candidate | bounded_candidate | 0 | no | bounded_global_corotational_frame3d_graph_candidate.v1; Bounded internal 3D graph candidate; the dense load-control solve uses shared source-bound 6DOF force/moment scaling with fail-closed real-binary64 source validation, residual-and-increment commit gates, strict scaled-residual-decreasing backtracking, final equilibrium reassembly, and parent-checkpoint immutability checks. |
| Stateful corotational fiber Frame3D | experimental | yes | yes | yes | no | bounded_candidate | state_checkpoint_candidate | 0 | no | bounded_stateful_corotational_fiber_frame3d_candidate.v1; Two- or three-point axial-biaxial fiber integration over a bounded Timoshenko reference; native sparse load control uses model-bound 6DOF force/moment scaling, residual-and-increment commit gates, strict residual-decreasing backtracking, exact material-response accepted-parent hash binding, material-specific steel/concrete/bond-slip admissibility through nested states, binary64-exact checkpoint displacement identity, deterministic unloaded genesis plus non-genesis nonzero-parent invariants, checkpoint-displacement material-state replay, final equilibrium reassembly, fail-closed scaled factorization diagnostics, and explicitly convergence-classified adaptive load cutback with rejected-trial rollback and exact accepted-checkpoint resume. A zero-update child is valid only when a changed load acts on restrained equations and every replay, factorization, reassembly, and equilibrium gate passes. |
| Frame3D direct displacement control | experimental | yes | yes | yes | no | bounded_candidate | state_checkpoint_candidate | 0 | no | stateful_corotational_frame3d_sparse_direct_displacement_control.v1; One free UX, UY, UZ, RX, RY, or RZ coordinate and one proportional reference-load factor are solved by a source-scaled sparse augmented Newton path with residual, increment, control, line-search, material-admissibility, final-reassembly, and factorization gates. Finite but constitutively unreachable bilinear-steel checkpoint states and target increments already inside the configured control tolerance fail before solving. Bounded adaptive target cutback retries only maximum-iteration or pure admissible merit-line-search failures, uses unit-specific minima plus depth/substep/whole-path attempt bounds, and hash-records every rejected target against an immutable accepted parent. |
| Mander monotonic confined concrete | experimental | yes | yes | yes | no | constitutive_candidate | state_lineage_candidate | 0 | no | mander_uniaxial_monotonic_compression.v1; Monotonic uniaxial compression envelope only. Stateful unloading, reversal, tension, and cyclic trials fail closed with unsupported_constitutive_path. |
| Cyclic bond-slip connector | experimental | yes | yes | yes | no | constitutive_candidate | state_lineage_candidate | 0 | no | bounded_cyclic_bond_slip_material_point.v1; Bounded SI-unit connector material point. |
| Steel-concrete partial composite interaction | experimental | yes | yes | yes | no | constitutive_candidate | state_lineage_candidate | 0 | no | condensed_single_slip_partial_composite_candidate.v1; Condensed single-slip-mode axial member coupling. |
| Nonlinear transient SDOF | experimental | yes | yes | yes | no | bounded_reference_candidate | checkpoint_replay_candidate | 0 | no | newmark_average_acceleration_bilinear_sdof_reference.v1; Fail-closed Newmark average-acceleration bilinear SDOF reference kernel. |
<!-- END GENERATED CAPABILITY SUPPORT -->
