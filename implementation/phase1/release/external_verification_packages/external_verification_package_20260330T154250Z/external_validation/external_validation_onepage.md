# External Validation One-Page

- Generated at: `2026-03-30T15:06:27.956197+00:00`
- Bundle id: `20260330T150627Z`

## Gate Status

- `nightly_release`: `PASS`
- `ci_gate`: `PASS`
- `static_validation`: `PASS`
- `freeze_release`: `PASS`
- `promotion`: `PASS`

## Integrity

- `signed_release_registry`: `PASS`
- `registry_signature_verified`: `PASS`
- `solver_hip_e2e`: `PASS`
- `rc_benchmark_lock`: `PASS`
- `ndtha_residual_gate`: `PASS`
- `committee_review_package`: `PASS`
- `midas_section_library_validator`: `MIDAS section-library: ok | 182/183 used | 183 templates | source=midas_parser_derived | implementation/phase1/open_data/midas/midas_generator_33.json`

## MIDAS Section Library

- `status`: `embedded metadata validated`
- `validator_line`: `MIDAS section-library: ok | 182/183 used | 183 templates | source=midas_parser_derived | implementation/phase1/open_data/midas/midas_generator_33.json`
- `consumers`: `nightly / release gap / committee dashboard / external validation onepage all consume the same validator line`

## Constitutive / Interaction Coverage

- `constitutive_interaction_families`: `expanded constitutive/interaction families are surfaced explicitly as shared summary lines across the release, committee, and external reports; the same lines are reused as-is.`
- `material_constitutive`: `Material constitutive gate: PASS | concrete_damage=yes(matrix=48/48,max=1.000) | cyclic_degradation=yes(matrix=46/46,residual_max=1.914%) | bond_interface=yes(matrix=48/48,bond_max=0.980) | creep_shrinkage=yes(matrix=7/7,mean=1.000/0.617) | soil_boundary_nonlinear=yes(matrix=11/11,profile=dense_sand) | device_dissipation=yes(matrix=10/10,types=3) | foundation_impedance_nonlinear=yes(matrix=19/19,links=6) | contact_link_hysteresis=yes(matrix=15/15,cats=6) | panel_zone_joint_response=yes(matrix=12/12,rows=12) | wind_dynamic_response=yes(matrix=16/16,topo=4) | track_support_viscoelasticity=yes(matrix=11/11,class=B) | vehicle_track_transient_coupling=yes(matrix=19/19,iters=1.64) | tunnel_soil_wave_attenuation=yes(matrix=13/13,dist=24) | serviceability_velocity_response=yes(matrix=8/8,pass_ratio=1.000) | construction_stage_redistribution=yes(matrix=6/6,diff=1) | joint_constraint_transfer=yes(matrix=5/5,rows=135) | aeroelastic_serviceability=yes(matrix=7/7,pass_ratio=1.000) | heterogeneous_soil_adaptation=yes(matrix=5/5,recall=1.000) | segment_joint_softening=yes(matrix=5/5,yield=53.000) | longitudinal_wave_strain_transfer=yes(matrix=5/5,strain=0.000000) | raw_pressure_field_mapping=yes(matrix=5/5,mapped=7278) | phase_assimilation_correction=yes(matrix=5/5,ratio=0.964) | multiscale_streaming_refinement=yes(matrix=5/5,chunk=16) | integrated_vibration_transfer=yes(matrix=5/5,checks=4) | resilience_ood_recovery=yes(matrix=5/5,steps=3) | boundary_absorption_nonlinear=yes(matrix=6/6,supports=2) | attention_load_localization=yes(matrix=6/6,peak=0.350) | residual_energy_stabilization=yes(matrix=7/7,solver=FIRE) | matrix=400/400 | groups=concrete_damage=48/48,cyclic_degradation=46/46,bond_interface=48/48,creep_shrinkage=7/7,soil_boundary_nonlinear=11/11,device_dissipation=10/10,foundation_impedance_nonlinear=19/19,contact_link_hysteresis=15/15,panel_zone_joint_response=12/12,wind_dynamic_response=16/16,track_support_viscoelasticity=11/11,vehicle_track_transient_coupling=19/19,tunnel_soil_wave_attenuation=13/13,serviceability_velocity_response=8/8,construction_stage_redistribution=6/6,joint_constraint_transfer=5/5,aeroelastic_serviceability=7/7,heterogeneous_soil_adaptation=5/5,segment_joint_softening=5/5,longitudinal_wave_strain_transfer=5/5,raw_pressure_field_mapping=5/5,phase_assimilation_correction=5/5,multiscale_streaming_refinement=5/5,integrated_vibration_transfer=5/5,resilience_ood_recovery=5/5,boundary_absorption_nonlinear=6/6,attention_load_localization=6/6,residual_energy_stabilization=7/7,phase_latency_projection=5/5,cache_window_adaptation=5/5,whitebox_feedback_stitching=5/5,recovery_residual_relock=5/5,rail_support_contact_modulation=5/5,tunnel_lining_interface_recovery=5/5,panel_feedback_residual_transfer=5/5,wind_pressure_coupled_transfer=5/5 | coverage=cd[t=2,h=2,s=2,sf=19],cyc[t=2,h=2,store=1,sf=18],bond[t=2,h=2,s=2,sf=18]`
- `surface_interaction`: `Surface interaction benchmark: PASS | ready=7/7 | family_matrix=420/420 | source_families=10/10 | shell_surface=yes | interface_transfer=yes | interface_gap=yes | foundation=yes | track_slab=yes | vehicle_track=yes | tunnel_lining_soil=yes | joint_panel=yes | ssi=yes | soil_tunnel=yes | direct_contact=6/6 | general_fe_coupling=yes | groups=modal-transfer=4/4,phase-assimilation-coupling=4/4,streaming-partition-coupling=4/4,integrated-vibration-coupling=4/4,resilience-recovery-coupling=4/4,kinematic-coupling=3/3,constraint-bridge=3/3,wave-radiation=2/2,boundary-absorption-coupling=4/4,attention-guided-transfer=4/4,residual-stabilization-coupling=4/4,solver-feedback-coupling=4/4,multiphysics-coupling=4/4,explicit-shear-transfer=4/4,phase-latency-coupling=4/4,cache-window-coupling=4/4,whitebox-feedback-coupling=4/4,recovery-residual-coupling=4/4,support-contact-modulation-coupling=4/4,lining-recovery-coupling=4/4,panel-feedback-coupling=4/4,pressure-mapping-coupling=4/4,shell-shell=53/53,shell-wall=81/81,footing-soil=62/62,track-slab=8/8,vehicle-track=8/8,tunnel-lining-soil=8/8,joint-panel=8/8,ssi=13/13,soil-tunnel=84/84,direct-contact=11/11`

## Nightly Smoke Probe

- `smoke_reason_code`: `PASS`
- `smoke_pass_rate`: `100.00%`
- `smoke_trial_feasible_rate`: `100.00%`
- `smoke_avg_trial_runtime_s`: `0.0557`
- `smoke_history_count`: `10`
- `smoke_strict_recommendation`: `candidate_for_strict_enable`

### Smoke Trend

- `smoke_history_png`: `implementation/phase1/release/release_gap_smoke_history.png`
- `runtime_drift`: baseline `1.3586s -> 1.3774s` (`+0.0188s`), trial `0.0553s -> 0.0555s` (`+0.0002s`)
- `max_dcr_drift`: baseline `0.9332 -> 0.9332` (`+0.0000`), trial `0.9332 -> 0.9332` (`+0.0000`)

![Nightly Smoke Trend](artifacts/implementation/phase1/release/release_gap_smoke_history.png)

### Recent Smoke Samples

| Sample | Generated | Pass | Trial Feasible | Baseline Runtime (s) | Trial Runtime (s) | Trial Max DCR | Action |
|---:|---|---|---|---:|---:|---:|---|
| 6 | 2026-03-30T13:33:18.377052+00:00 | True | True | 1.4648 | 0.0555 | 0.9332 | connection_detailing_down |
| 7 | 2026-03-30T13:57:14.403720+00:00 | True | True | 1.4324 | 0.0540 | 0.9332 | connection_detailing_down |
| 8 | 2026-03-30T13:58:15.190727+00:00 | True | True | 1.3860 | 0.0559 | 0.9332 | connection_detailing_down |
| 9 | 2026-03-30T14:33:48.013233+00:00 | True | True | 1.3798 | 0.0560 | 0.9332 | connection_detailing_down |
| 10 | 2026-03-30T14:37:33.867618+00:00 | True | True | 1.3774 | 0.0555 | 0.9332 | connection_detailing_down |

### Measured Chain Category Trend

- `measured_chain_category_png`: `implementation/phase1/release/release_gap_measured_chain_categories.png`

![Measured Chain Category Trend](artifacts/implementation/phase1/release/release_gap_measured_chain_categories.png)

## Key Metrics

- `commercial_grade`: `Commercial`
- `deployment_model`: `engineer_in_the_loop_accelerated_coverage`
- `accelerated_coverage_target`: `95-99%`
- `residual_holdout_target`: `1-5%`
- `estimated_time_saved`: `91-96%`
- `measured_chain_wall_clock_comparable_rolling_min`: `1.03` (N=14, range=0.87-2.0)
- `measured_chain_wall_clock_min`: `0.87`
- `comparable_run_selection_mode`: `current_pipeline_comparable_full_chain_pass`
- `comparable_reference_deployment_model`: `engineer_in_the_loop_accelerated_coverage`
- `comparable_reference_strict_smoke`: `True`
- `engineer_in_loop_accelerated_coverage_ready`: `True`
- `empirical_smoke_runtime_reduction`: `95.9-96.23%`
- `estimated_time_saved_basis`: `Empirical estimate derived from nightly design-optimization smoke runtime reduction, scaled by the accelerated-coverage target. smoke_mean_runtime_saved=96.02%, sample_count=10.`
- `time_saving_focus`: `Use this engine to automate the dominant, time-consuming 95-99% of repeated analysis, screening, packaging, and optimization workflows. Keep the residual 1-5% under licensed engineer review, legacy-tool cross-check, and formal sign-off workflows.`
- `full_commercial_replacement_ready`: `False`
- `external_benchmark_submission_ready_to_start_now`: `True`
- `external_benchmark_submission_ready_to_start_full_submission_now`: `False`
- `external_benchmark_submission_reason_code`: `PASS_START_NOW_LIMITED`
- `external_benchmark_submission_recommended_start_mode`: `start_now_limited_external_benchmark`
- `external_benchmark_submission_recommended_submission_scope`: `component_and_system_performance_benchmark_with_review_boundary`
- `external_benchmark_submission_blocker_label`: `none`
- `external_benchmark_submission_caution_label`: `panel_zone_external_validation_only_boundary, audit_review_queue_pending=2`
- `external_benchmark_execution_mode`: `limited`
- `external_benchmark_execution_ready_task_count`: `10`
- `external_benchmark_execution_blocked_task_count`: `2`
- `external_benchmark_execution_review_boundary_pending_count`: `2`
- `external_benchmark_execution_review_boundary_resolution_label`: `approve_all=PASS_START_NOW_FULL/ready_full=yes; reject_one=ERR_ARCHITECTURE_BLOCKERS/open_revision=1`
- `external_benchmark_execution_review_boundary_owner_label`: `licensed_engineer=2`
- `external_benchmark_execution_review_boundary_assignee_label`: `unassigned=2`
- `external_benchmark_execution_review_boundary_assignment_status_label`: `unassigned=2`
- `external_benchmark_execution_review_boundary_priority_label`: `high=1, medium=1`
- `external_benchmark_execution_review_boundary_family_label`: `connection_detailing=1, detailing=1`
- `external_benchmark_execution_review_boundary_change_count_total`: `11`
- `external_benchmark_execution_review_boundary_followup_action_label`: `wait_for_review=2`
- `external_benchmark_execution_review_boundary_sla_state_label`: `within_sla=2`
- `external_benchmark_execution_review_boundary_age_bucket_label`: `lt_24h=2`
- `external_benchmark_execution_review_boundary_overdue_count`: `0`
- `external_benchmark_execution_review_boundary_oldest_open_age_hours`: `0.477`
- `external_benchmark_execution_status_mode`: `execution_complete_no_fail`
- `external_benchmark_execution_planned_task_count`: `0`
- `external_benchmark_execution_in_progress_task_count`: `0`
- `external_benchmark_execution_completed_task_count`: `10`
- `external_benchmark_execution_failed_task_count`: `0`
- `external_benchmark_execution_finished_task_count`: `10`
- `external_benchmark_execution_completion_ratio`: `1.000`
- `audit_review_decision_batch_template_item_count`: `2`
- `audit_review_decision_batch_template_current_status_label`: `pending_review=2`
- `audit_review_decision_batch_template_review_owner_label`: `licensed_engineer=2`
- `audit_review_decision_batch_template_review_priority_label`: `high=1, medium=1`
- `audit_review_decision_batch_attested_example_count`: `2`
- `audit_review_decision_batch_attested_example_preview_label`: `approve_all=PASS_START_NOW_FULL, mixed=ERR_ARCHITECTURE_BLOCKERS`
- `external_benchmark_submission_preview_approve_all_reason_code`: `PASS_START_NOW_FULL`
- `external_benchmark_submission_preview_approve_all_ready_full`: `True`
- `external_benchmark_submission_preview_approve_all_pending_count`: `0`
- `external_benchmark_submission_preview_approve_all_open_revision_count`: `0`
- `external_benchmark_submission_preview_reject_one_reason_code`: `ERR_ARCHITECTURE_BLOCKERS`
- `external_benchmark_submission_preview_reject_one_ready_full`: `False`
- `external_benchmark_submission_preview_reject_one_pending_count`: `0`
- `external_benchmark_submission_preview_reject_one_open_revision_count`: `1`
- `external_benchmark_submission_preview_reject_one_blocker_label`: `audit_review_resolution_has_open_revisions`
- `audit_review_decision_batch_runner_reason_code`: `PASS`
- `audit_review_decision_batch_runner_apply_live`: `False`
- `audit_review_decision_batch_runner_live_applied`: `False`
- `audit_review_decision_batch_runner_preview_reason_code`: `PASS_START_NOW_FULL`
- `audit_review_decision_batch_runner_preview_ready_full`: `True`
- `audit_review_decision_batch_runner_preview_pending_count`: `0`
- `audit_review_decision_batch_runner_preview_open_revision_count`: `0`
- `structural_optimization_viewer_html`: `implementation/phase1/release/visualization/structural_optimization_viewer.html`
- `structural_optimization_viewer_mode`: `static_release_artifact_viewer`
- `structural_optimization_viewer_story_zone_nonempty_cell_count`: `16`
- `structural_optimization_viewer_story_zone_max_abs_cost_proxy_delta`: `308.750`
- `structural_optimization_viewer_gallery_tile_count`: `7`
- `promotion_reason_code`: `PASS`
- `promotion_hold_for_review`: `False`
- `hold_review_manifest`: `implementation/phase1/release/hold_review_manifest.json`
- `hold_review_packet_md`: `implementation/phase1/release/hold_review_packet.md`
- `hold_review_packet_pdf`: `implementation/phase1/release/hold_review_packet.pdf`
- `hold_review_ack_json`: `implementation/phase1/release/hold_review_ack.json`
- `open_gap_counts`: `P0=1, P1=0, P2=0`
- `midas_element_rows_total`: `12728`
- `midas_element_rows_skipped`: `0`
- `midas_unknown_row_total`: `0`
- `midas_semantic_load_binding_pass`: `True`
- `midas_use_stld_block_count`: `2`
- `midas_semantic_load_case_count`: `6`
- `midas_semantic_load_combination_count`: `8`
- `midas_bound_unbound_load_rows`: `nodal=12/0, selfweight=1/0, pressure=7278/0`
- `mgt_export_artifact_exists`: `True`
- `mgt_export_contract_pass`: `True`
- `mgt_export_support_mode`: `bounded_patch_subset`
- `mgt_export_supported_change_count`: `36`
- `mgt_export_unsupported_change_count`: `0`
- `mgt_export_direct_patch_change_count`: `25`
- `mgt_export_direct_patch_action_family_label`: `beam_section=1, connection_detailing=6, detailing=5, perimeter_frame=1, rebar=5, slab_thickness=2, wall_thickness=5`
- `mgt_export_rebar_payload_namespace_mode`: `group_local`
- `mgt_export_rebar_delivery_mode`: `direct_patch_eligible`
- `mgt_export_evidence_model`: `direct_patch_plus_audit_review_manifest`
- `mgt_export_delivery_boundary`: `direct_patch=beam_section=1, connection_detailing=6, detailing=5, perimeter_frame=1, rebar=5, slab_thickness=2, wall_thickness=5 | sidecar=n/a | connection_payload=direct_patch_metadata_plus_sidecar | detailing_payload=direct_patch_metadata_plus_sidecar`
- `mgt_export_rebar_payload_material_level_namespace_present`: `True`
- `mgt_export_rebar_payload_group_local_namespace_present`: `True`
- `mgt_export_material_level_rebar_payloads`: `3/5`
- `mgt_export_group_local_rebar_payload_row_count`: `6/6`
- `mgt_export_connection_detailing_payload_namespace_mode`: `group_local`
- `mgt_export_connection_detailing_payload_group_local_namespace_present`: `True`
- `mgt_export_group_local_connection_detailing_payload_row_count`: `6/6`
- `mgt_export_connection_detailing_direct_patch_eligible_change_count`: `6`
- `mgt_export_detailing_payload_namespace_mode`: `group_local`
- `mgt_export_detailing_payload_group_local_namespace_present`: `True`
- `mgt_export_group_local_detailing_payload_row_count`: `5/5`
- `mgt_export_detailing_direct_patch_eligible_change_count`: `5`
- `mgt_export_connection_detailing_structured_payload_mapped_change_count`: `6`
- `mgt_export_detailing_structured_payload_mapped_change_count`: `5`
- `mgt_export_connection_detailing_delivery_mode`: `direct_patch_metadata_plus_sidecar`
- `mgt_export_detailing_delivery_mode`: `direct_patch_metadata_plus_sidecar`
- `mgt_export_rebar_direct_patch_eligible_change_count`: `6`
- `mgt_export_patched_material_row_count`: `24`
- `mgt_export_cloned_material_count`: `24`
- `mgt_export_rebar_direct_patch_ineligible_reason_label`: ``
- `mgt_export_rebar_direct_patch_mapping_source_label`: `alt_slab_wall_group_id=5, direct_group_id=1`
- `mgt_export_instruction_sidecar_change_count`: `0`
- `mgt_export_instruction_sidecar_action_family_label`: `n/a`
- `mgt_export_instruction_sidecar_audit_only_action_family_label`: `connection_detailing=6, detailing=5` (11)
- `mgt_export_instruction_sidecar_manual_input_action_family_label`: `n/a` (0)
- `mgt_export_audit_review_manifest_action_family_label`: `connection_detailing=6, detailing=5` (11)
- `mgt_export_audit_review_packet_action_family_label`: `connection_detailing=1, detailing=1` (2)
- `mgt_export_audit_review_packet_followup_type_label`: `connection_detailing_audit_after_material_patch=1, detailing_audit_after_material_patch=1`
- `mgt_export_audit_review_packet_file_action_family_label`: `connection_detailing=1, detailing=1` (2)
- `mgt_export_audit_review_queue_action_family_label`: `connection_detailing=1, detailing=1` (2)
- `mgt_export_audit_review_queue_status_label`: `pending_review=2`
- `mgt_export_audit_review_followup_action_label`: `wait_for_review=2` (2)
- `mgt_export_audit_review_followup_owner_label`: `licensed_engineer=2`
- `mgt_export_audit_review_followup_review_owner_label`: `licensed_engineer=2`
- `mgt_export_audit_review_followup_status_label`: `pending_review=2`
- `mgt_export_audit_review_followup_sla_state_label`: `within_sla=2`
- `mgt_export_audit_review_followup_age_bucket_label`: `lt_24h=2`
- `mgt_export_audit_review_followup_overdue_item_count`: `0`
- `mgt_export_audit_review_resolution_action_label`: `await_review_decision=2` (2)
- `mgt_export_audit_review_resolution_owner_label`: `licensed_engineer=2`
- `mgt_export_audit_review_resolution_status_label`: `pending_review=2`
- `mgt_export_instruction_sidecar_review_priority_label`: ``
- `mgt_export_instruction_sidecar_followup_type_label`: ``
- `mgt_export_cloned_section_count`: `0`
- `mgt_export_cloned_thickness_count`: `6`
- `mgt_export_retargeted_element_row_count`: `418`
- `kds_compliance_rows`: `511`
- `kds_member_check_rows`: `1056`
- `kds_clause_count`: `16`
- `ndtha_residual_top_m_max_abs`: `0.6880580090188355`
- `ndtha_residual_drift_pct_max_abs`: `1.9136000000000006`
- `ndtha_residual_fallback_rate`: `0.0`
- `registry_artifact_count`: `9`
- `design_opt_long_feasible`: `True`
- `design_opt_long_final_max_dcr`: `0.9331636363636363`
- `design_opt_raw_max_drift_pct`: `9.200000000000003`
- `design_opt_repaired_compliance_max_drift_pct`: `1.9872000000000005`
- `design_opt_compliance_basis`: `repaired_solver_validated_slice`
- `design_opt_repair_action_count`: `1`
- `design_opt_constructability_signal_gain_pct`: `0.8158195424350374`
- `design_opt_constructability_avg`: `0.32955670560576916 -> 0.3268681175980322`
- `design_opt_detailing_complexity_avg`: `0.44354114999544225 -> 0.4417926006724248`
- `design_opt_selected_family_mix`: `beam_section=4, connection_detailing=6, detailing=5, perimeter_frame=1, rebar=5, slab_thickness=4, wall_thickness=7`
- `design_opt_selected_dominant_family`: `wall_thickness` (21.88%)
- `design_opt_selected_family_mix_trend`: `beam_section=+0, connection_detailing=+0, detailing=+0, perimeter_frame=+0, rebar=+0, slab_thickness=+0, wall_thickness=+0`
- `design_opt_previous_dominant_family`: `wall_thickness` (21.88%)
- `design_opt_preview_supply_family_mix`: `beam_section=8, connection_detailing=9, detailing=164, perimeter_frame=1, rebar=276, slab_thickness=48, wall_thickness=204`
- `design_opt_preview_missing_target_families`: ``
- `design_opt_cost_delta`: `903.4629446021863`
- `design_opt_changed_group_count`: `25`
- `design_opt_blocked_action_row_count`: `50`
- `design_opt_blocked_illegal_by_mask`: `0`
- `design_opt_blocked_illegal_by_mask_family_label`: ``
- `design_opt_blocked_no_cost_gain`: `9`
- `design_opt_blocked_constructability_hard_gate`: `5`
- `design_opt_blocked_constructability_hard_gate_label`: `detailing_ratio_above_hard_limit=5`
- `design_opt_blocked_constructability_hard_gate_family_label`: `beam_section=2, rebar=3`
- `design_opt_blocked_no_cost_group_count`: `5`
- `design_opt_blocked_no_cost_explain_row_count`: `5`
- `design_opt_entrypoint_report_count`: `7`
- `design_opt_entrypoint_pass_count`: `7`

## Advanced Holdouts

- `pbd_dynamic_hinge_refresh_ready`: `True` (computed_member_local_hinge_refresh)
- `pbd_hinge_refresh_reason`: `Dynamic hinge-refresh artifact is attached.`
- `pbd_hinge_refresh_artifact_present`: `True`
- `pbd_hinge_refresh_artifact_kind`: `hinge_refresh_projected_from_optimization_changes`
- `pbd_hinge_refresh_source_mode`: `rebar_sensitive_member_local_refresh`
- `pbd_hinge_refresh_overlap_member_count`: `88`
- `pbd_hinge_refresh_rebar_sensitive_member_count`: `70`
- `pbd_hinge_benchmark_gate_pass`: `True`
- `pbd_hinge_benchmark_fixture_regression_pass`: `True`
- `pbd_hinge_benchmark_alignment_pass`: `True`
- `pbd_hinge_benchmark_asset_count`: `5`
- `pbd_hinge_benchmark_split`: `train=2, val=2, holdout=1`
- `pbd_hinge_benchmark_rebar_sensitive_count`: `1`
- `pbd_hinge_benchmark_confinement_sensitive_count`: `1`
- `pbd_hinge_benchmark_fixture_count`: `5`
- `pbd_hinge_benchmark_fixture_min_point_count`: `449`
- `pbd_hinge_benchmark_fixture_min_peak_drift_ratio`: `0.03662513089005235`
- `pbd_hinge_benchmark_alignment_refresh_column_row_count`: `5`
- `pbd_hinge_benchmark_alignment_rebar_sensitive_column_count`: `5`
- `pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_min`: `0.0127`
- `pbd_hinge_benchmark_alignment_benchmark_rebar_ratio_max`: `0.0603`
- `pbd_hinge_benchmark_alignment_refresh_rebar_ratio_min`: `0.064`
- `pbd_hinge_benchmark_alignment_refresh_rebar_ratio_max`: `0.074`
- `panel_zone_3d_clash_ready`: `True` (internal_engine_panel_zone_3d_clash_and_anchorage_complete)
- `panel_zone_constructability_reason`: `Internal engine completed panel-zone joint geometry, anchorage, and clash recomputation with validated member overlap; external verification now serves as an optional audit boundary.`
- `panel_zone_source_contract_mode`: `topology_projected_3d_clash_and_anchorage_bridge`
- `panel_zone_internal_engine_complete`: `False`
- `panel_zone_external_validation_pending`: `False`
- `panel_zone_validation_boundary`: ``
- `panel_zone_source_artifact_kind`: `design_optimization_dataset_npz`
- `panel_zone_proxy_candidate_count`: `45`
- `panel_zone_instruction_sidecar_present`: `True`
- `panel_zone_instruction_sidecar_change_count`: `0`
- `panel_zone_instruction_sidecar_candidate_overlap_mode`: `none`
- `panel_zone_instruction_sidecar_overlap_row_count`: `0`
- `panel_zone_instruction_sidecar_overlap_member_count`: `0`
- `panel_zone_instruction_sidecar_evidence_model`: `direct_patch_plus_audit_review_manifest`
- `panel_zone_instruction_sidecar_rebar_delivery_mode`: `direct_patch_eligible`
- `panel_zone_validated_source_row_count_total`: `135`
- `panel_zone_validated_source_overlap_member_count_min`: `45`
- `panel_zone_missing_required_sources`: ``
- `panel_zone_solver_verified_inbox_status_mode`: `empty_without_history`
- `panel_zone_solver_verified_pending_input`: `False`
- `panel_zone_solver_verified_latest_consume_contract_pass`: `False`
- `panel_zone_solver_verified_source_origin_class`: ``
- `panel_zone_solver_verified_release_refresh_source_allowed`: `False`
- `panel_zone_solver_verified_recommended_action`: `wait_for_solver_drop`
- `foundation_optimization_ready`: `True` (active_foundation_member_optimization)
- `foundation_optimization_reason`: `foundation optimization artifact is attached and dataset contains foundation members`
- `foundation_scope_source`: `dataset_summary`
- `foundation_artifact_scan_mode`: `npz_full`
- `upstream_foundation_label_count`: `0` (dataset_scope_only)
- `wind_tunnel_raw_mapping_ready`: `True` (raw_hffb_node_pressure_mapping)
- `wind_tunnel_mapping_reason`: `Raw wind-tunnel HFFB mapping is ready for traceable MIDAS binding.`

## Binary Metrics

| Area | Cases | Key Metric A | Key Metric B | Interpretation |
|---|---:|---|---|---|
| Frame | 3 | drift p95=4.167% | top-disp p95=3.485% | nonlinear frame regression envelope |
| Wind | 4 | max drift=0.000806% | residual drift=0.000113% | long-duration across-wind serviceability |
| SSI | 4 | nonlinear span=0.282342 | residual drift=0.004034% | fixed-vs-SSI residual reduction |
| Design Opt | 17 rows | raw drift=9.2000%, repaired drift=1.9872% | cost delta=903.463 | raw vs repaired compliance slice kept separate |

## Time-Saving Coverage

- `estimated_time_saved`: `91-96%`
- `measured_chain_wall_clock_comparable_rolling_min`: `1.03` (N=14, range=0.87-2.0)
- `measured_chain_wall_clock_min`: `0.87`
- `comparable_run_selection_mode`: `current_pipeline_comparable_full_chain_pass`
- `comparable_reference_deployment_model`: `engineer_in_the_loop_accelerated_coverage`
- `comparable_reference_strict_smoke`: `True`
- `empirical_smoke_runtime_reduction`: `95.9-96.23%`
- `basis`: `Empirical estimate derived from nightly design-optimization smoke runtime reduction, scaled by the accelerated-coverage target. smoke_mean_runtime_saved=96.02%, sample_count=10.`
- `Use this engine to automate the dominant, time-consuming 95-99% of repeated analysis, screening, packaging, and optimization workflows. Keep the residual 1-5% under licensed engineer review, legacy-tool cross-check, and formal sign-off workflows.`

## Residual Holdout Boundary

| Category | Owner | Relative Share | Absolute Project % | Scope |
|---|---|---:|---|---|
| Licensed Engineer Review | 기술사 | 50% | 0.5-2.5% | non-standard interpretation, final judgment, exceptional irregularity, and member-level edge cases |
| Legacy Tool Cross-Validation | 기존툴+기술사 | 30% | 0.3-1.5% | novel load paths, authority-critical submodels, and residual niche workflows outside the accelerated envelope |
| Legal Sign-Off | 기술사/기존 승인 workflow | 20% | 0.2-1.0% | formal seal, legal submission, and authority-facing responsibility that remains outside automated scope |

## Residual Holdout Review Table

| Category | Axis | Detail | Owner | Why |
|---|---|---|---|---|
| Licensed Engineer Review | review_story_zone | S04/perimeter (2), S01/intermediate (1), S02/perimeter (1), S03/intermediate (1) | 기술사 | Top story-zone review pockets are derived from actual accepted design-change rows so engineer holdout stays tied to the highest-touch parts of the structure. |
| Licensed Engineer Review | story_band | 4, 3, 6 | 기술사 | High-touch story bands remain under engineer review because they concentrate accepted design changes and irregular response checks. |
| Licensed Engineer Review | member_family | wall (28), slab (20), beam (20) | 기술사 | Dominant member families in accepted optimization changes still require engineer judgment on local edge cases and detailing intent. |
| Licensed Engineer Review | zone | perimeter (9), intermediate (6), core (1) | 기술사 | Zone concentration is used to focus manual review on the highest-touch portions of the structural layout. |
| Legacy Tool Cross-Validation | submodel_family | SCBF16B (3), SCBF16B_shell_beam_mix (2), nheri_case01_sensor (1), nheri_case02_sensor (1) | 기존툴+기술사 | Authority submodel families are derived from the active catalog paths so cross-validation follows the exact benchmark submodels still outside the accelerated envelope. |
| Legacy Tool Cross-Validation | authority_critical_case | SAC (3), NHERI (3), OpenSees (2) | 기존툴+기술사 | Authority-critical benchmark tracks remain the primary cross-validation target outside the accelerated envelope. |
| Legacy Tool Cross-Validation | authority_catalog_case_id | SAC20_LA_holdout_01, SAC20_SEA_holdout_02, SAC20_BOS_holdout_03, NHERI_UCSD_like_holdout_01, NHERI_UCSD_like_holdout_02, NHERI_UCSD_like_holdout_03 | 기존툴+기술사 | Authority catalog case ids are read directly so the holdout review list refreshes automatically when the benchmark catalog changes. |
| Legal Sign-Off | authority_catalog_track | sac (3), nheri (3), opensees (2) | 기술사/기존 승인 workflow | Formal authority-facing responsibility is anchored to the active authority catalog tracks and remains outside the automated responsibility boundary. |
| Legal Sign-Off | authority_critical_case | sealed submission pack, authority-facing variants, stamped final issue | 기술사/기존 승인 workflow | Formal authority-facing deliverables remain outside the automated responsibility boundary. |

## Residual Holdout Routing Matrix

| Category | Track | Submodel | Review Story/Zone | Member Family | Owner | Why |
|---|---|---|---|---|---|---|
| Legacy Tool Cross-Validation | opensees | SCBF16B | S04/perimeter | wall | 기존툴+기술사 | Routing matrix links active authority submodels to dominant story/zone/member-family review pockets so the remaining manual and legacy-tool work stays explicit. |
| Legacy Tool Cross-Validation | opensees | SCBF16B_shell_beam_mix | S01/intermediate | slab | 기존툴+기술사 | Routing matrix links active authority submodels to dominant story/zone/member-family review pockets so the remaining manual and legacy-tool work stays explicit. |
| Legacy Tool Cross-Validation | sac | SCBF16B | S02/perimeter | beam | 기존툴+기술사 | Routing matrix links active authority submodels to dominant story/zone/member-family review pockets so the remaining manual and legacy-tool work stays explicit. |
| Legacy Tool Cross-Validation | sac | SCBF16B_shell_beam_mix | S03/intermediate | column | 기존툴+기술사 | Routing matrix links active authority submodels to dominant story/zone/member-family review pockets so the remaining manual and legacy-tool work stays explicit. |
| Legacy Tool Cross-Validation | nheri | nheri_case01_sensor | S04/perimeter | wall | 기존툴+기술사 | Routing matrix links active authority submodels to dominant story/zone/member-family review pockets so the remaining manual and legacy-tool work stays explicit. |
| Legacy Tool Cross-Validation | nheri | nheri_case02_sensor | S01/intermediate | slab | 기존툴+기술사 | Routing matrix links active authority submodels to dominant story/zone/member-family review pockets so the remaining manual and legacy-tool work stays explicit. |

## Authority Catalog Routing Diff

- `baseline_seeded`: `False` | `changes=0` | `added=0` | `removed=0` | `unchanged=7`

- No authority-catalog routing changes detected for this external submission refresh.

## Blocked Cost-Down Actions

- `blocked_rows`: `50`
- `illegal_by_mask`: `0`
- `illegal_by_mask_families`: ``
- `no_cost_gain`: `9`
- `constructability_hard_gate`: `5`
- `constructability_hard_gate_reasons`: `detailing_ratio_above_hard_limit=5`
- `no_cost_gain_groups`: `5`
- `no_cost_gain_explain_rows`: `5`

## Design Optimization Entrypoint Groups

- `Ablation` reports=`1/1` pass=`1` fail=`0` all_pass=`True`
- `Dataset` reports=`1/1` pass=`1` fail=`0` all_pass=`True`
- `Profile` reports=`1/1` pass=`1` fail=`0` all_pass=`True`
- `Stage A` reports=`2/2` pass=`2` fail=`0` all_pass=`True`
- `Stage A/B/C` reports=`1/1` pass=`1` fail=`0` all_pass=`True`
- `Stage B` reports=`1/1` pass=`1` fail=`0` all_pass=`True`

## Appendix: Design Optimization Entrypoint Details

<details>
<summary>Ablation (1 rows, pass=1, fail=0, reasons=PASS:1)</summary>

- `ablation` group=`Ablation` pass=`True` reason=`PASS` | report=`/home/betelgeuze/건축구조분석/implementation/phase1/release/design_optimization/design_optimization_ablation_report.json`

</details>

<details>
<summary>Dataset (1 rows, pass=1, fail=0, reasons=PASS:1)</summary>

- `dataset` group=`Dataset` pass=`True` reason=`PASS` | report=`/home/betelgeuze/건축구조분석/implementation/phase1/release/design_optimization/design_optimization_dataset_report.json`

</details>

<details>
<summary>Profile (1 rows, pass=1, fail=0, reasons=PASS:1)</summary>

- `objective_profile` group=`Profile` pass=`True` reason=`PASS` | report=`/home/betelgeuze/건축구조분석/implementation/phase1/release/design_optimization/design_objective_profile_report.json`

</details>

<details>
<summary>Stage A (2 rows, pass=2, fail=0, reasons=PASS:2)</summary>

- `solver_loop` group=`Stage A` pass=`True` reason=`PASS` | report=`/home/betelgeuze/건축구조분석/implementation/phase1/release/design_optimization/design_optimization_solver_loop_report.json`
- `solver_loop_long` group=`Stage A` pass=`True` reason=`PASS` | report=`/home/betelgeuze/건축구조분석/implementation/phase1/release/design_optimization/design_optimization_solver_loop_long_report.json`

</details>

<details>
<summary>Stage A/B/C (1 rows, pass=1, fail=0, reasons=PASS:1)</summary>

- `budgeted` group=`Stage A/B/C` pass=`True` reason=`PASS` | report=`/home/betelgeuze/건축구조분석/implementation/phase1/release/design_optimization/design_optimization_budgeted_report.json`

</details>

<details>
<summary>Stage B (1 rows, pass=1, fail=0, reasons=PASS:1)</summary>

- `cost_reduction` group=`Stage B` pass=`True` reason=`PASS` | report=`/home/betelgeuze/건축구조분석/implementation/phase1/release/design_optimization/design_optimization_cost_reduction_report.json`

</details>


## Appendix: MIDAS KDS Row Provenance Export

- `summary`: `MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144 | clause_filters=6 | member_filters=12 | reverse_jump=viewer_subset_reverse_jump_v11`
- `artifacts`: json=`implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.json` | csv=`implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv` | report=`implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json`
- `row-provenance sync`: `the Review surface and row-provenance appendix stay bidirectionally aligned on the same Hazard and Rule Family slices; the appendix exposes explicit viewer_row_url and viewer_slice_url reverse-sync links back to the matching viewer row and slice.`

| Combination | Member | Clause | Baseline Focus | Mode | Clause Provenance | Member Inventory |
|---|---|---|---|---|---|---|
| gLCB1 | C-TST-003 | KDS-MOMENT-Y-001 | 27441 | exact row-level provenance | rows=12 | members=12 | rules=1 | hazards=3 | review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column |
| gLCB1 | C-TRN-005 | KDS-MOMENT-Y-001 | 27441 | exact row-level provenance | rows=12 | members=12 | rules=1 | hazards=3 | review=C-TRN-005 | case=C-TRN-005 | baseline=27441 | member_types=column |
| gLCB1 | C-TST-003 | KDS-INT-FRAME-001 | 27441 | exact row-level provenance | rows=12 | members=12 | rules=1 | hazards=3 | review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column |
| gLCB1 | C-TST-001 | KDS-MOMENT-Y-001 | 27441 | exact row-level provenance | rows=12 | members=12 | rules=1 | hazards=3 | review=C-TST-001 | case=C-TST-001 | baseline=27441 | member_types=column |
| gLCB1 | C-TST-003 | KDS-SHEAR-Y-001 | 27441 | exact row-level provenance | rows=12 | members=12 | rules=1 | hazards=3 | review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column |
| gLCB1 | C-TRN-005 | KDS-INT-FRAME-001 | 27441 | exact row-level provenance | rows=12 | members=12 | rules=1 | hazards=3 | review=C-TRN-005 | case=C-TRN-005 | baseline=27441 | member_types=column |
| gLCB1 | C-TRN-007 | KDS-MOMENT-Y-001 | 27425 | exact row-level provenance | rows=12 | members=12 | rules=1 | hazards=3 | review=C-TRN-007 | case=C-TRN-007 | baseline=27425 | member_types=wall |
| gLCB1 | C-TST-003 | KDS-AXIAL-001 | 27441 | exact row-level provenance | rows=12 | members=12 | rules=1 | hazards=3 | review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column |

| Clause | Rows | Members | Combos | Top Member | Top D/C |
|---|---|---|---|---|---|
| KDS-AXIAL-001 | 24 | 12 | 2 | C-TST-003 | 1.065 |
| KDS-INT-FRAME-001 | 24 | 12 | 2 | C-TST-003 | 1.137 |
| KDS-MOMENT-Y-001 | 24 | 12 | 2 | C-TST-003 | 1.216 |
| KDS-MOMENT-Z-001 | 24 | 12 | 2 | C-TST-003 | 0.991 |
| KDS-SHEAR-Y-001 | 24 | 12 | 2 | C-TST-003 | 1.110 |
| KDS-SHEAR-Z-001 | 24 | 12 | 2 | C-TST-003 | 0.863 |

| Member | Baseline Focus | Rows | Clauses | Combos | Top Clause |
|---|---|---|---|---|---|
| C-TRN-001 | 26878 | 12 | 6 | 2 | KDS-MOMENT-Y-001 |
| C-TRN-002 | 27287 | 12 | 6 | 2 | KDS-MOMENT-Y-001 |
| C-TRN-003 | 26878 | 12 | 6 | 2 | KDS-MOMENT-Y-001 |
| C-TRN-004 | 27425 | 12 | 6 | 2 | KDS-MOMENT-Y-001 |
| C-TRN-005 | 27441 | 12 | 6 | 2 | KDS-MOMENT-Y-001 |
| C-TRN-006 | 27287 | 12 | 6 | 2 | KDS-MOMENT-Y-001 |
| C-TRN-007 | 27425 | 12 | 6 | 2 | KDS-MOMENT-Y-001 |
| C-TST-001 | 27441 | 12 | 6 | 2 | KDS-MOMENT-Y-001 |

| Hazard | Rows | Members | Clauses | Combos | Top Clause | Top D/C |
|---|---|---|---|---|---|---|
| combined | 48 | 4 | 6 | 2 | KDS-MOMENT-Y-001 | 1.216 |
| seismic | 48 | 4 | 6 | 2 | KDS-MOMENT-Y-001 | 1.112 |
| wind | 48 | 4 | 6 | 2 | KDS-MOMENT-Y-001 | 0.809 |

| Rule Family | Rows | Members | Hazards | Combos | Top Clause | Top D/C |
|---|---|---|---|---|---|---|
| strength | 120 | 12 | 3 | 2 | KDS-MOMENT-Y-001 | 1.216 |
| strength_interaction | 24 | 12 | 3 | 2 | KDS-INT-FRAME-001 | 1.137 |

## Submission Note

- This bundle is the current external-validation submission baseline.
- Previous external-validation submission bundles were pruned after this package was created.
