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

## Developer CPU and GPU execution options

These options retain the existing model, material, recovery and result contracts.
They do not establish external validation or release readiness. Select each option
explicitly and compare the same returned work before interpreting timings.

The Rust CLI accepts an inline ModelIR batch manifest and emits one completed JSON
artifact to stdout. For example, create a one-case manifest from the supported fixture:

```bash
python3 - <<'PY'
import json
from pathlib import Path
model = json.loads(Path("native/distribution/frame-alpha-cantilever.model-ir.json").read_text())
manifest = {
    "schema_version": "structural-native-frame3d-batch-request.v1",
    "batch_id": "example-batch",
    "resource_policy": {
        "profile": "bounded_frame3d_single_thread_workers.v1",
        "workers": 1,
        "cpu_budget": 1,
    },
    "requests": [{"case_id": "cantilever", "model": model,
                  "load_pattern_id": "LC_WEAK", "result_id": "example-result"}],
}
with Path("frame-batch.json").open("x") as stream:
    json.dump(manifest, stream)
PY
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  OMP_MAX_ACTIVE_LEVELS=1 OMP_NESTED=FALSE \
  native/target/release/structural-cli model analyze-frame3d-batch frame-batch.json
```

Build the executable with `cargo build --release --locked --manifest-path
native/Cargo.toml -p structural-cli`; a custom `CARGO_TARGET_DIR` changes its location.
The manifest accepts 1–1024 cases and 1–12 workers. `cpu_budget` must fit observed
available parallelism, and workers must fit that explicit budget. Case and result
identifiers must be unique; select exactly one load pattern or combination per case.
The fixed native kernel uses one thread per worker. Thread declarations, if present,
must match this strict single-thread profile even when a named BLAS library is unused.
The command reads these declarations without changing its process environment.
This admission is per invocation, not a machine-wide or cross-process CPU quota.
Ordered outcomes preserve each request's validation, compile, solve, recovery and
ResultIR gates. Exit 0 means every case succeeded; exit 1 includes completed batches
with case errors; invalid manifest/resource admission uses exit 2. No output-file
paths are accepted: stdout contains the selected artifact, and callers own file
publication. Independent-model throughput is distinct from single-model solve time.

The optional OpenMP steel library supports reusable prepared buffers and a batch of
integration-point trials sharing one fiber-law layout:

```python
from structural_analysis.materials.native_steel_batch import NativeSteelBatch, use_native_steel_batch

backend = NativeSteelBatch("build/steel/libstructural_steel_batch.so", workers=1, prepared=True)
with use_native_steel_batch(backend):
    response = section.integrate(generalized_strain, accepted_parent)
```

See [native build instructions](native/README.md#optional-openmp-steel-batch).
`prepared=True` reuses packed material data and scratch storage; compatible element
integration points can share a native call. Accepted parents remain immutable, and
point/fiber accumulation order, material laws, commit/rollback and failure checks
remain unchanged. Shared prepared scratch rejects concurrent use. Python remains
the default, and full Python response reconstruction can outweigh native arithmetic.

The fixed-chord public RC API also accepts
`PublicRCFiberFrameConfig(matrix_backend="scipy_sparse_spsolve_cpu")`. Its CLI equivalent is:

```bash
python -m structural_analysis.api.nonlinear_fiber_frame_cli \
  examples/public_rc_fiber_frame_cantilever.json --load-steps 2 \
  --matrix-backend scipy_sparse_spsolve_cpu \
  --out rc-sparse-result.json --report-out rc-sparse-report.json \
  --checkpoint-out rc-sparse-checkpoint-chain.json
```

The default stays `numpy_linalg_solve_dense` (reported as `numpy_dense_ndarray`).
Sparse Newton trials assemble the free CSR tangent directly and use the existing
unregularized CPU solver. Exact-conditioning admission remains capped at 256 free
equations; terminal engineering receipts retain the existing dense assembler.
This does not make the entire path sparse or lift a model, convergence or conditioning
limit. Within one public invocation, eligible pure schema/hash computations and
unchanged sparse factorizations may be reused. Changed values are rechecked;
numerical replay, source binding, array commitments and semantic gates still run.
Canonical JSON uses a fast normalization path for exact built-in values, with
identical bytes, signed-zero rules and fresh containers. NumPy, custom, deep and
invalid values retain the original normalization and error handling.

Use the source-bound public RC driver to separate API timing from an optional
diagnostic profile. Choose a new output filename for every run:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -B scripts/benchmark_rc_execution_pipeline.py \
  --source-root "$PWD" --output /tmp/rc-pipeline-dense.json \
  --cases 1x2 --repetitions 5 --elapsed-budget-seconds 300 --profile
```

Cases are `1x2`, `2x2`, `4x2` (members × section layers) and `1x16`; all use
two load steps. Add `--matrix-backend scipy_sparse_spsolve_cpu` for sparse execution,
or `--steel-library build/steel/libstructural_steel_batch.so --steel-workers 1
--prepared` for the explicit prepared native option. The timer covers the same
analyze-plus-validate API for the first call and every steady sample; it excludes
startup, imports, input preparation, hashing and report writes. Every result and
checkpoint is fingerprinted outside timing and must repeat exactly within the same
backend. Backend metadata is removed only from the comparison fingerprint, not the
saved result configuration. The separate `--profile` call saves raw pstats and
mutually exclusive self-time categories; its time is not a steady sample. Peak RSS
is process-lifetime usage including imports and inputs, not isolated solver memory.
Reports retain completed and interrupted work. Python signal budgets can be delayed
inside native calls; use an external supervisor for a hard process timeout.

The HIP sequence driver keeps intermediate states/residuals on the GPU and compares
the same generated fixed-operator update sequence with host-roundtrip GPU execution
and a preassembled-CSR OpenMP CPU implementation:

```bash
python3 scripts/benchmark_hip_residual_pipeline.py --out /tmp/hip-sequence \
  --dimensions 1536 12288 49152 --batches 1 8 32 --steps 8 32 \
  --workers 1 2 4 8 12 --samples 7
```

This developer driver builds its benchmark adapters unless `--reuse-library` is
selected. Operator setup, transfers, device phases and transfer-inclusive wall time
have separate scopes. It evaluates a fixed linear sequence, not nonlinear RC
convergence or a public GPU solver. Compare only identical sequence inputs and
returned final state/residual; CPU batch and GPU sequence gains cannot be multiplied.

## License boundary

The root `LICENSE` is the authority for repository-authored source and is all-rights-reserved: it
grants no use, modification, distribution, sublicensing, sale, or derivative-work permission without
a separate written agreement from the applicable rights holder. Native Cargo crates inherit that
file rather than an MIT/Apache expression. Dependency allowlist and SBOM checks are technical
inventory controls only; product-license approval, commercial redistribution, and third-party
redistribution clearance remain blocked pending explicit human/legal decisions. The repository-owned
rights-holder trust root currently contains no approved signer. License closure can pass only with an
RSA-SHA256 decision from a non-revoked approved signer that binds the exact Git commit, root-license
hash, tracked license-policy artifact and covered paths, decision ID, tier, approver role, product
scope, and an explicit validity window of at most 90 days. The decision still cannot grant
third-party-material redistribution or overall release authority.

## Readiness source of truth

- The only current-main status authority is the source-bound, attested `artifacts/manifests/product_state.current.v1.json` inside the successful `Product State Current` artifact for the exact commit. If that exact-SHA artifact is missing, failed, unattested, or inconsistent, current status is unavailable and receives no promotion credit.
- Checked-in readiness, capability, matrix, and clean-runner snapshots are historical diagnostics or source-discovery surfaces. They are not current-main authority, and their volatile blocker or coverage counts must not be copied into current claims. `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json` is one such historical snapshot; inspect it without rewriting protected evidence with `python3 scripts/build_product_readiness_snapshot.py --json --no-write`.
- The following tracked readiness summaries preserve their own recorded context and may be useful for gap history, but every current claim must be taken from the exact-current Product State artifact.
- Repository documentation makes no release-promotion claim: release_ready=`false`. This conservative boundary does not replace or broaden the exact-current Product State authority above.
- Open Benchmark Developer Preview readiness: `implementation/phase1/release_evidence/productization/developer_preview_readiness.json` and `implementation/phase1/release_evidence/productization/developer_preview_readiness.md` report developer_preview_ready=`false`. Their volatile blocker counts remain historical snapshot data and are not current-main authority. The included scope is public/open benchmark import, deterministic analysis/reporting, benchmark scorecard review, and a local GUI review workflow.
- Developer Preview excludes permit automation, structural engineer replacement, multi-tenant SaaS/account/license server operation, and independent AI/GNN/surrogate truth claims. The customer shadow, license approval, commercial SLA, 30-run CI streak, and external approval receipt remain Commercial Release evidence rather than Developer Preview claims. The new feature freeze `frozen_until_developer_preview_baseline_is_clean`, AI training freeze `frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed`, and GPU/HIP track `performance_track_after_cpu_reference_parity` keep AI/GNN/surrogate truth behind the deterministic reference solver, residual/Jacobian/Newton closure, and benchmark truth.
- Developer Preview RC status: `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json` and `implementation/phase1/release_evidence/productization/developer_preview_rc_status.md` report status `blocked`, deliverables `10/10`, and final gates `5/9`. The remaining boundary keeps selected medium models, silent import loss zero, Linux/Windows reproducibility, and human new-user workflow observation open; clean-clone and large crash/OOM-free execution are ready. This does not close full Phase 3, G1 full nonlinear full-mesh/material Newton, Linux/Windows parity, or the human new-user workflow observation.
- The canonical PM blocker register reports release areas `4/16`, open blocker handoff `72`, release-area blockers `51`, external input-required blockers `10`, and local remediation-ready blockers `62`. These are handoff counts, not release promotion.
- `python3 scripts/report_release_evidence_freshness.py` currently reports `1/14` passing receipts, including the tracked `developer_preview_rc_status.json` surface. Missing or stale receipts keep Developer Preview RC final gates and Commercial Release claims blocked.
- Release-mode checks use `python3 scripts/check_github_actions_self_hosted_runner_status.py --check --fail-blocked` and `python3 scripts/build_product_readiness_snapshot.py --check` without rewriting tracked evidence. A runner query failure remains a blocker; `--write-query-error-evidence` is an explicit diagnostic write.

<!-- BEGIN GENERATED CAPABILITY SUPPORT -->
## Generated capability support matrix

This table is generated from the v2 registry at `artifacts/manifests/capabilities.yaml`. Do not edit it directly. `implemented` and `executable` do not mean `public`; numerical, recovery, external-V&V, and release authority remain independent.

Current status authority is the source-bound, attested exact-commit `artifacts/manifests/product_state.current.v1.json` contained in the successful `.github/workflows/product-state-current.yml` artifact. Checked-in capability and readiness snapshots are historical/discovery surfaces only; missing or unverifiable exact-current evidence receives no credit, and volatile coverage counts are not copied into this registry.

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
| Corotational 2D fiber frame | experimental | yes | yes | yes | no | bounded_j1_j5_and_exact_engineering_recovery_candidate | bounded_j1_j5_and_exact_engineering_recovery_candidate | 0 | no | corotational_connected_frame2d.v1; Connected planar load-control remains experimental and non-public. Exact-current clean-runner and cross-environment status is reported only by the source-bound, attested Product State Current CI artifact; tracked receipts are historical inputs and grant no current credit. Independent operator attestation and Level 2 promotion remain absent, so external_vv_level stays 0. Direct displacement control remains lower-level only. Prescribed-only iterative paths with free equations and no force reference fail closed until a source-bound kinematic reference-force scaling contract exists. No other member-feature family, design, or release authority is created. |
| Native sparse nonlinear backend | experimental | yes | yes | yes | no | bounded_native_coo_csr_and_fail_closed_exact_conditioning_candidate | not_applicable | 0 | no | corotational_element_triplet_coalesce_sorted_csr_fp64_plus_blocked_exact_1536.v1; The public exact-conditioning path remains bounded to 256 equations. A separate CPU-only blocked exact diagnostic is bounded to 1536 equations and is integrated only into the bounded experimental 3D graph candidate. Exact inverse-column conditioning has quadratic work and does not close production-scale policy, performance or memory evidence, external V&V, or release promotion. |
| OpenSees Level 2 verification | blocked | yes | yes | yes | no | none | not_applicable | 0 | no | independent_operator_promotion_gate_v1; Pinned external comparison values and tracked receipts are historical inputs only. Exact-current coverage, freshness, clean-runner parity, blockers, and counts are authoritative only in the source-bound, attested Product State Current CI artifact for the exact commit; the registry intentionally carries no volatile coverage total. Missing or unverifiable exact-current evidence receives no credit. Independent operator identity, project legal approvals, complete scientific decisions, and a signed promotion decision remain absent. The Level 2 gate remains blocked, external_vv_level stays 0, and no design, commercial-equivalence, or release authority is granted. |
| Second independent solver Level 2 verification | blocked | yes | no | no | no | none | not_applicable | 0 | no | independent_operator_promotion_required; Tracked CalculiX and clean-runner receipts are historical inputs and never establish current status. Exact-current same-operator execution and cross-environment parity are credited only when an attested clean-runner artifact for the exact commit is attached to the Product State Current artifact; absent or invalid evidence fails closed. Independent operator attestation, legal review, broader coverage, and second-solver Level 2 promotion remain absent. |
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
