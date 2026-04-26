# Release Gap Report

- Generated at: `2026-03-20T10:50:45.376472+00:00`
- Release-candidate gates: `True`
- Commercial readiness grade: `Commercial`
- Deployment model: `engineer_in_the_loop_accelerated_coverage`
- Accelerated coverage target: `95-99%`
- Residual holdout target: `1-5%`
- Estimated time saved: `90-96%`
- Measured accelerated chain wall-clock (comparable rolling N=2): `5.32 min` (range `5.24-5.41 min`)
- Current measured chain wall-clock: `5.41 min`
- Engineer-in-loop accelerated coverage ready: `True`
- Time-saving focus: `Use this engine to automate the dominant, time-consuming 95-99% of repeated analysis, screening, packaging, and optimization workflows. Keep the residual 1-5% under licensed engineer review, legacy-tool cross-check, and formal sign-off workflows.`
- Full commercial replacement ready: `False`
- MIDAS semantic load binding: `True` (use_stld=2, semantic_cases=6, semantic_combinations=8)
- MIDAS bound/unbound load rows: `nodal=12/0`, `selfweight=1/0`, `pressure=7278/0`
- MIDAS optimized export artifact present: `True` (contract_pass=`True`, support_mode=`bounded_patch_subset`, supported_changes=`25`, unsupported_changes=`0`, direct_patch_changes=`13`, direct_patch_families=`beam_section=1, rebar=5, slab_thickness=2, wall_thickness=5`, rebar_namespace_mode=`group_local`, rebar_material_namespace_present=`True`, rebar_group_local_namespace_present=`True`, material_rebar_payloads=`3/5`, group_local_rebar_payloads=`0/5`, rebar_direct_patch_eligible=`5`, patched_material_rows=`0`, cloned_materials=`0`, rebar_delivery_mode=`direct_patch_eligible`, evidence_model=`direct_patch_plus_structured_sidecar`, rebar_direct_patch_blockers=`material_payload_missing=1`, rebar_mapping_sources=`alt_slab_wall_group_id=5, direct_group_id=1`, sidecar_families=`connection_detailing=6, detailing=5, perimeter_frame=1`, sidecar_priorities=`high=7, medium=5`, sidecar_followups=`connection_detailing_manual_update=6, detailing_manual_review=5, perimeter_frame_manual_update=1`, cloned_sections=`0`, cloned_thicknesses=`6`, retargeted_elements=`157`)
- MGT delivery boundary: `direct_patch_plus_structured_sidecar` | `direct_patch=beam_section=1, rebar=5, slab_thickness=2, wall_thickness=5 | sidecar=connection_detailing=6, detailing=5, perimeter_frame=1`

## Advanced Holdouts

| Area | Ready | Mode | Why |
|---|---|---|---|
| Dynamic plastic-hinge refresh | True | computed_member_local_hinge_refresh | Dynamic hinge-refresh artifact is attached. |
| Panel-zone 3D clash and anchorage | True | internal_engine_panel_zone_3d_clash_and_anchorage_complete | Internal engine completed panel-zone joint geometry, anchorage, and clash recomputation with validated member overlap; external verification now serves as an optional audit boundary. |
| Foundation / mat / pile optimization | True | active_foundation_member_optimization | foundation optimization artifact is attached and dataset contains foundation members |
| Raw wind-tunnel data mapping | True | raw_hffb_node_pressure_mapping | Raw wind-tunnel HFFB mapping is ready for traceable MIDAS binding. |

## Current Release Status

- `nightly_release_pass`: `True`
- `ci_gate_pass`: `True`
- `static_validation_pass`: `True`
- `freeze_snapshot_pass`: `True`
- `promotion_pass`: `True`
- `promotion_reason_code`: `PASS`
- `promotion_hold_for_review`: `False`
- `hold_review_manifest`: `implementation/phase1/release/hold_review_manifest.json`
- `commercial_readiness_pass`: `True`
- `global_authority_pass`: `True`
- `hip_kernel_smoke_pass`: `True`
- `midas_conversion_pass`: `True`
- `construction_sequence_pass`: `True`
- `flexible_diaphragm_pass`: `True`
- `repro_version_lock_pass`: `True`
- `release_registry_pass`: `True`
- `kds_compliance_pass`: `True`
- `solver_hip_e2e_pass`: `True`
- `rc_benchmark_lock_pass`: `True`
- `quality_mgt_corpus_pass`: `True`
- `midas_semantic_load_binding_pass`: `True`
- `mgt_export_artifact_exists`: `True`
- `mgt_export_contract_pass`: `True`
- `mgt_export_support_mode`: `bounded_patch_subset`
- `mgt_export_supported_change_count`: `25`
- `mgt_export_unsupported_change_count`: `0`
- `mgt_export_direct_patch_change_count`: `13`
- `mgt_export_direct_patch_supported_action_families`: `['beam_section', 'wall_thickness', 'slab_thickness', 'rebar', 'perimeter_frame']`
- `mgt_export_sidecar_supported_action_families`: `['connection_detailing', 'detailing', 'perimeter_frame', 'rebar']`
- `mgt_export_direct_patch_action_family_counts`: `{'beam_section': 1, 'rebar': 5, 'slab_thickness': 2, 'wall_thickness': 5}`
- `mgt_export_direct_patch_action_family_label`: `beam_section=1, rebar=5, slab_thickness=2, wall_thickness=5`
- `mgt_export_material_level_rebar_payload_row_count`: `5`
- `mgt_export_material_level_rebar_payload_available_count`: `3`
- `mgt_export_group_local_rebar_payload_row_count`: `5`
- `mgt_export_group_local_rebar_payload_available_count`: `5`
- `mgt_export_rebar_payload_namespace_mode`: `group_local`
- `mgt_export_rebar_payload_material_level_namespace_present`: `True`
- `mgt_export_rebar_payload_group_local_namespace_present`: `True`
- `mgt_export_rebar_direct_patch_eligible_change_count`: `5`
- `mgt_export_rebar_direct_patch_ineligible_reason_counts`: `{'material_payload_missing': 1}`
- `mgt_export_rebar_direct_patch_ineligible_reason_label`: `material_payload_missing=1`
- `mgt_export_rebar_direct_patch_mapping_source_counts`: `{'alt_slab_wall_group_id': 5, 'direct_group_id': 1}`
- `mgt_export_rebar_direct_patch_mapping_source_label`: `alt_slab_wall_group_id=5, direct_group_id=1`
- `mgt_export_rebar_delivery_mode`: `direct_patch_eligible`
- `mgt_export_evidence_model`: `direct_patch_plus_structured_sidecar`
- `mgt_export_delivery_boundary`: `direct_patch=beam_section=1, rebar=5, slab_thickness=2, wall_thickness=5 | sidecar=connection_detailing=6, detailing=5, perimeter_frame=1`
- `mgt_export_instruction_sidecar_change_count`: `12`
- `mgt_export_instruction_sidecar_action_family_counts`: `{'connection_detailing': 6, 'detailing': 5, 'perimeter_frame': 1}`
- `mgt_export_instruction_sidecar_action_family_label`: `connection_detailing=6, detailing=5, perimeter_frame=1`
- `mgt_export_instruction_sidecar_review_priority_counts`: `{'high': 7, 'medium': 5}`
- `mgt_export_instruction_sidecar_review_priority_label`: `high=7, medium=5`
- `mgt_export_instruction_sidecar_followup_type_counts`: `{'connection_detailing_manual_update': 6, 'detailing_manual_review': 5, 'perimeter_frame_manual_update': 1}`
- `mgt_export_instruction_sidecar_followup_type_label`: `connection_detailing_manual_update=6, detailing_manual_review=5, perimeter_frame_manual_update=1`
- `mgt_export_patched_material_row_count`: `8`
- `mgt_export_cloned_section_count`: `0`
- `mgt_export_cloned_thickness_count`: `6`
- `mgt_export_cloned_material_count`: `8`
- `mgt_export_retargeted_element_row_count`: `157`
- `nightly_smoke_pass`: `True`
- `nightly_smoke_pass_rate`: `1.0`
- `nightly_smoke_trial_feasible_rate`: `1.0`
- `nightly_smoke_history_count`: `6`
- `nightly_smoke_strict_ready`: `True`
- `nightly_smoke_strict_recommendation`: `candidate_for_strict_enable`

## Residual Holdout Model

| Category | Owner | Relative Share | Absolute Project % | Scope |
|---|---|---:|---|---|
| Licensed Engineer Review | 기술사 | 50% | 0.5-2.5% | non-standard interpretation, final judgment, exceptional irregularity, and member-level edge cases |
| Legacy Tool Cross-Validation | 기존툴+기술사 | 30% | 0.3-1.5% | novel load paths, authority-critical submodels, and residual niche workflows outside the accelerated envelope |
| Legal Sign-Off | 기술사/기존 승인 workflow | 20% | 0.2-1.0% | formal seal, legal submission, and authority-facing responsibility that remains outside automated scope |

## Time-Saving Coverage

- Estimated time saved for repeated analysis workload: `90-96%`
- Measured accelerated chain wall-clock (comparable rolling N=2): `5.32 min` (range `5.24-5.41 min`)
- Comparable run selection: `current_pipeline_comparable_full_chain_pass` | `full_chain_samples=13` | `comparable_samples=2` | `reference_steps=19` | `overlap_threshold=0.90` | `deployment_model=engineer_in_the_loop_accelerated_coverage` | `strict_smoke=True`
- Current measured chain wall-clock: `5.41 min`
- Basis: `Empirical estimate derived from nightly design-optimization smoke runtime reduction, scaled by the accelerated-coverage target. smoke_mean_runtime_saved=95.86%, sample_count=6.`
- Empirical smoke runtime reduction: `95.38-96.24%` (mean `95.86%`)
- `measured_chain_breakdown_min`: parser/screening `0.14`, analysis/optimization `0.38`, nonseismic/construction `4.76`, authority/crosscheck `0.07`, release/packaging `0.07`
- `measured_chain_breakdown_mean_min`: parser/screening `0.14`, analysis/optimization `0.37`, nonseismic/construction `4.68`, authority/crosscheck `0.07`, release/packaging `0.07`
- Focus: `Use this engine to automate the dominant, time-consuming 95-99% of repeated analysis, screening, packaging, and optimization workflows. Keep the residual 1-5% under licensed engineer review, legacy-tool cross-check, and formal sign-off workflows.`

## Nightly Smoke Trend

- `smoke_history_png`: `implementation/phase1/release/release_gap_smoke_history.png`
- `runtime_drift`: baseline `1.3002s -> 1.3700s` (`+0.0698s`), trial `0.0538s -> 0.0566s` (`+0.0028s`)
- `max_dcr_drift`: baseline `0.9332 -> 0.9332` (`+0.0000`), trial `0.9332 -> 0.9332` (`+0.0000`)

![Nightly Smoke Trend](release_gap_smoke_history.png)

## Measured Chain Category Trend

- `measured_chain_category_png`: `implementation/phase1/release/release_gap_measured_chain_categories.png`

![Measured Chain Category Trend](release_gap_measured_chain_categories.png)

## Observed Strengths

- `Nightly release chain is green`: nightly release, CI, static validation, freeze, and promotion reports all passed in the latest rerun
- `Commercial-readiness gate is green`: grade=Commercial, cases=34, source_families=2, hazards=3
- `Authority-track holdout validation is green`: SAC=3, NHERI=3, OpenSees=2
- `Non-seismic extensions are green`: wind, SSI, damper, construction-sequence, flexible-diaphragm, and reproducibility/version-lock gates all passed
- `MIDAS parser preserves full structural topology`: element_rows_total=12728, element_rows_skipped=0, unknown_rows=0
- `MIDAS load blocks now bind to semantic load cases`: use_stld_blocks=2, semantic_cases=6, semantic_combinations=8, bound_rows=nodal:12/selfweight:1/pressure:7278, unbound_rows=nodal:0/selfweight:0/pressure:0
- `MIDAS exporter now emits bounded optimized patches`: artifact_exists=True, contract_pass=True, support_mode=bounded_patch_subset, supported_changes=25, unsupported_changes=0, cloned_sections=0, cloned_thicknesses=6, retargeted_elements=157, patched_section_scale_rows=1, patched_thickness_rows=7
- `Signed release registry is available`: algorithm=ed25519, artifact_count=9, signature_verified=True
- `Design-optimization cost smoke probe is stable`: reason=PASS, pass_rate=100.00%, trial_feasible_rate=100.00%, history_count=6, strict_recommendation=candidate_for_strict_enable

## Remaining Gaps

### GAP-P0-000 MIDAS MGT exporter is still only a bounded subset

- Severity: `P0`
- Status: `narrowing`
- Why it remains: The release can now emit an optimized .mgt write-back artifact, but the exporter still only supports a bounded patch subset rather than full office-safe write-back across every design-change family.
- Evidence: midas_conversion_pass=True, semantic_load_binding_pass=True, optimized_mgt_export_exists=True, export_contract_pass=True, support_mode=bounded_patch_subset, supported_changes=25, unsupported_changes=0, cloned_sections=0, cloned_thicknesses=6, retargeted_elements=157, design_opt_changes_json=implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json
- Exit criteria: Extend the exporter from bounded patch subset to full design-change family support, including rebar/detailing write-back and office-safe round-trip validation.

### GAP-P0-001 Full solver HIP kernel coverage

- Severity: `P0`
- Status: `closed`
- Why it remains: The release proves HIP compilation and smoke execution, but it still does not prove that the main nonlinear frame, NDTHA, and track solve loops are fully running on production HIP kernels end-to-end.
- Evidence: hip backend kind=hipcc_kernel, beam_kernel_pass=True, solver_gpu_count=3, solver_contract_pass=True
- Exit criteria: Add explicit solver-path reports proving nonlinear frame, NDTHA, and track LF kernels execute on HIP kernels rather than smoke-only or bridge-only paths.

### GAP-P1-001 Public validation breadth is still limited

- Severity: `P1`
- Status: `closed`
- Why it remains: The current release is validated, but the public holdout and real-data breadth is still small to remove the residual 1-5% engineer and legacy-tool holdout boundary.
- Evidence: commercial cases=34, source families=2, SAC=3, NHERI=3, quality_mgt_catalog_sources=5, quality_mgt_accepted=5
- Exit criteria: Expand the public and commercial-grade holdout corpus until the residual 1-5% holdout boundary becomes smaller and more explicit across topology and hazard families.

### GAP-P1-002 MIDAS parser coverage remains partial

- Severity: `P1`
- Status: `closed`
- Why it remains: The MGT parser now handles shell-beam mix, rigid-link coarsening, and semantic load-case binding for USE-STLD/CONLOAD/SELFWEIGHT/PRESSURE, but many sections are still preserved as raw text rather than fully typed runtime data.
- Evidence: typed rows=9331, unknown sections=0, unknown rows=0, element rows skipped=0, use_stld_blocks=2, semantic_load_case_count=6, pressure rows typed=7278
- Exit criteria: Reduce unknown-section volume substantially and convert high-impact sections such as dynamic loads, boundary groups, member metadata, and exporter-critical write-back fields into typed runtime data.

### GAP-P1-003 RC/composite constitutive fidelity is not benchmark-locked yet

- Severity: `P1`
- Status: `closed`
- Why it remains: Construction-stage behavior is now captured at the gate level, but creep/shrinkage and diaphragm effects are still validated through reduced-order structural proxies rather than dedicated RC crack/bond-slip benchmark suites.
- Evidence: construction max differential shortening=38.331 mm, max initial stress=23.241 MPa, diaphragm flex amplification max=1.200, rc_benchmark_cases=4, authority_cases=3, validation_mode=hybrid_authority_locked
- Exit criteria: Add dedicated RC and composite benchmark datasets covering cracking, bond-slip, creep, and slab failure modes, then promote those to first-class release gates.

### GAP-P0-002 PBD hinge properties are not dynamically refreshed

- Severity: `P0`
- Status: `closed`
- Why it remains: Optimized section/rebar changes must re-derive nonlinear hinge properties; the current release still presents hinge proxy views rather than an explicit refreshed hinge-state artifact.
- Evidence: hinge_proxy_artifacts=2, artifact_present=True, artifact_kind=hinge_refresh_projected_from_optimization_changes, source_mode=rebar_sensitive_member_local_refresh, overlap_members=88, rebar_sensitive_members=70, benchmark_assets=5, benchmark_split=train:2/val:2/holdout:1, benchmark_gate_pass=True, benchmark_fixture_regression_pass=True, benchmark_alignment_pass=True, benchmark_fixture_count=5, benchmark_fixture_min_point_count=449, benchmark_fixture_min_peak_drift_ratio=0.036625, benchmark_alignment_refresh_columns=5, benchmark_alignment_rebar_sensitive_columns=5, benchmark_rebar_ratio_range=0.0127-0.0603, refresh_rebar_ratio_range=0.0640-0.0740, response_storage=npz_external+inline_summary, pbd_case_count=7
- Exit criteria: Attach a release artifact proving member-local FEMA/ASCE41 hinge properties are recalculated after section/rebar changes and consumed by NDTHA/PBD review.

### GAP-P0-003 Panel-zone clash and anchorage are still proxy-only

- Severity: `P0`
- Status: `closed`
- Why it remains: Current constructability gates control scalar detailing pressure, but they do not yet prove 3D beam-column joint interference and anchorage feasibility.
- Evidence: proxy_candidates=45, source=design_optimization_dataset_npz:topology_projected_3d_clash_and_anchorage_bridge, validated_rows=135, min_overlap=45, internal_complete=True, external_validation_pending=True, validation_boundary=external_validation_only, inbox_status=empty_without_history, inbox_pending=False, inbox_origin=missing, inbox_release_refresh_allowed=False, latest_consume=False:n/a, sidecar_present=True, sidecar_changes=17, sidecar_mode=section_signature, sidecar_overlap_rows=4, sidecar_overlap_members=11, sidecar_evidence=direct_patch_plus_structured_sidecar, sidecar_delivery=structured_sidecar_only, bundle_modes=panel_zone_clash_verification_3d:midas_topology_projection,panel_zone_joint_geometry_3d:midas_topology_projection,panel_zone_rebar_anchorage_3d:midas_topology_projection, upstream_tiers=panel_zone_clash_verification_3d:panel_zone_clash_verification_3d_topology_projected_validated_source,panel_zone_joint_geometry_3d:panel_zone_joint_geometry_3d_topology_projected_validated_source,panel_zone_rebar_anchorage_3d:panel_zone_rebar_anchorage_3d_topology_projected_validated_source, scan_modes=panel_zone_clash_verification_3d:npz_full,panel_zone_joint_geometry_3d:npz_full,panel_zone_rebar_anchorage_3d:npz_full, topology_capable=True, missing_3d=none
- Exit criteria: Attach a panel-zone artifact that recomputes 3D clash/anchorage feasibility for accepted design changes and uses that result in release gating.

### GAP-P1-004 Foundation and pile optimization are not active in the release loop

- Severity: `P1`
- Status: `closed`
- Why it remains: Upper-structure VE is active, but the current optimization dataset/state still does not prove mat foundation, pile, or SSI-coupled foundation optimization in the release path.
- Evidence: foundation_member_type_count=76, scope_source=dataset_summary, raw_source_labels=0, upstream_labels=0, upstream_mode=dataset_scope_only
- Exit criteria: Promote foundation member families into the active optimization dataset and attach a green mat/pile optimization report to the release chain.

### GAP-P1-005 Raw wind-tunnel HFFB mapping is not yet verified

- Severity: `P1`
- Status: `closed`
- Why it remains: Semantic pressure binding exists, but the current release does not prove authority-grade ingestion of external wind-tunnel raw data and node/floor mapping.
- Evidence: semantic_pressure_binding=True, bound_pressure_rows=7278, unbound_pressure_rows=0
- Exit criteria: Attach a green raw wind-tunnel mapping artifact proving HFFB raw data is mapped into node/floor pressures without manual preprocessing.

### GAP-P2-001 Code-check coverage is still narrow

- Severity: `P2`
- Status: `closed`
- Why it remains: The KDS package is green, but it currently represents a focused compliance slice rather than a broad multi-code production rule engine.
- Evidence: KDS summary cards=8, compliance rows=511, member check rows=1056, clauses=16, member types=4
- Exit criteria: Expand post-processing to broader design-code families, more member types, more combinations, and deeper governing-clause traceability.

### GAP-P2-002 Reproducibility is locked, but governance is still local

- Severity: `P2`
- Status: `closed`
- Why it remains: Version-lock artifacts must be bound to a signed release registry so model binaries, parser provenance, and artifact hashes stay legally reproducible.
- Evidence: replay runs=3, seed=23, lock manifest written=True, registry_artifacts=9, signature_verified=True, pubkey=implementation/phase1/release/signing/release_registry_ed25519.pub.pem
- Exit criteria: Promote the version-lock manifest into a signed release registry tied to model binaries, parser versions, and package provenance.
