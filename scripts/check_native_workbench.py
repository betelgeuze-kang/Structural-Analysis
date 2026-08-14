#!/usr/bin/env python3
"""Verify bounded Rust-native Workbench C5 ownership and executable evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/Cargo.toml": ('"crates/structural-workbench"',),
    "native/crates/structural-workbench/src/lib.rs": (
        "structural-native-workbench-session.v1",
        "WorkbenchStageV1",
        "execute_model_ir_native_analysis",
        "execute_native_mgt_import",
        "initialize_model_ir_linear_from_mgt_paths",
        "execute_external_comparison",
        "execute_pdf_report",
        "execute_localized_pdf_report",
        "write_atomic_file",
        "fs::rename",
        "workbench_stage_gap",
        "workbench_artifact_inventory_mismatch",
        "workbench_mgt_import_binding_mismatch",
        "structural-native-workbench-view.v1",
        "structural-native-workbench-review.v1",
        "structural-native-workbench-export.v1",
        "publish_review",
        "inspect_json",
        "linear_report_text",
        "ndtha_response_view_text",
        "ndtha_response_view_text_localized",
        "fixed_guided_deformed_shape_view_text",
        "fixed_guided_deformed_shape_view_text_localized",
        "export_localized_pdf",
        "render_model_topology_view",
        "render_model_topology_view_file_localized",
        "render_model_topology_view_localized",
        "export_json",
        "workbench_review_binding_mismatch",
    ),
    "native/crates/structural-workbench/src/report_view.rs": (
        "structural-native-workbench-linear-report.v1",
        "WorkbenchReportLocaleV1",
        '"en-US"',
        '"ko-KR"',
        "safe_terminal_text",
        "not WCAG, PDF/UA",
    ),
    "native/crates/structural-workbench/src/result_view.rs": (
        "structural-native-workbench-ndtha-response-view.v1",
        "WorkbenchResultChannelV1",
        '"top-displacement"',
        '"drift-ratio"',
        '"base-shear"',
        '"residual-inf"',
        "WORKBENCH_RESULT_VIEW_MAX_COUNT_V1",
        "ResultIR v1 does not carry dt_s",
        "not a time reconstruction, 3D/deformed/modal/contour view",
        "시간값을 추론하지 않습니다",
    ),
    "native/crates/structural-workbench/src/deformed_view.rs": (
        "structural-native-workbench-fixed-guided-deformed-view.v1",
        "fixed_guided_frame3d_x",
        "validate_model_bytes",
        "Top displacement global X (m)",
        "C++ fixed-guided adapter execution",
        "C++ 고정-가이드 어댑터 실행",
        'semantic_snapshot_value: "verified"',
        "not_general_nodal_displacement_3d_modal_contour",
    ),
    "native/crates/structural-workbench/src/model_view.rs": (
        "structural-native-model-topology-view.v1",
        "ModelTopologyProjectionV1",
        "validate_model_bytes",
        'semantic_snapshot: "C++ semantic snapshot"',
        "Structural Native Workbench - 모델 위상 뷰",
        "C++ 의미 스냅샷",
        "workbench_model_view_semantics_invalid",
        "bounded_general_modelir_semantic_snapshot_terminal_topology_projection",
    ),
    "native/crates/structural-workbench/src/model_edit.rs": (
        "structural-native-model-edit-receipt.v1",
        "structural-native:model-edit-node.v1",
        "structural-native:model-add-node.v1",
        "structural-native:model-delete-orphan-node.v1",
        "structural-native:model-edit-nodal-load.v1",
        "structural-native:model-edit-nodal-load-target.v1",
        "nodal_load_target",
        "structural-native:model-edit-nodal-load-identity.v1",
        "nodal_load_identity_edit",
        "structural-native:model-edit-linear-load-pattern-identity.v1",
        "linear_load_pattern_identity_edit",
        "structural-native:model-edit-linear-material-identity.v1",
        "linear_material_identity_edit",
        "structural-native:model-edit-frame-section-identity.v1",
        "frame_section_identity_edit",
        "structural-native:model-edit-constraint-target.v1",
        "constraint_target",
        "structural-native:model-delete-fixed-constraint-dof.v1",
        "fixed_constraint_dof_delete",
        "structural-native:model-add-fixed-constraint-dof.v1",
        "fixed_constraint_dof_add",
        "structural-native:model-reorder-fixed-constraint-dof.v1",
        "fixed_constraint_dof_reorder",
        "structural-native:model-edit-fixed-constraint-identity.v1",
        "fixed_constraint_identity_edit",
        "structural-native:model-edit-constraint-value.v1",
        "structural-native:model-edit-linear-material.v1",
        "structural-native:model-edit-frame-section.v1",
        "structural-native:model-edit-truss-section.v1",
        "structural-native:model-edit-frame-element-orientation.v1",
        "structural-native:model-edit-frame-element-properties.v1",
        "structural-native:model-edit-truss-element-properties.v1",
        "structural-native:model-edit-element-connectivity.v1",
        "structural-native:model-add-frame3d-member.v1",
        "structural-native:model-add-truss3d-member.v1",
        "structural-native:model-delete-frame3d-leaf-member.v1",
        "structural-native:model-delete-truss3d-leaf-member.v1",
        "structural-native:model-add-nodal-load.v1",
        "structural-native:model-delete-nodal-load.v1",
        "structural-native:model-add-fixed-constraint.v1",
        "structural-native:model-delete-fixed-constraint.v1",
        "structural-native:model-add-linear-load-pattern.v1",
        "structural-native:model-add-linear-load-combination.v1",
        "structural-native:model-add-direct-linear-load-combination.v2",
        "structural-native:model-edit-direct-linear-load-combination-factor.v1",
        "direct_linear_load_combination_factor_edit",
        "structural-native:model-edit-direct-linear-load-combination-reference.v1",
        "direct_linear_load_combination_reference_edit",
        "structural-native:model-add-direct-linear-load-combination-term.v1",
        "direct_linear_load_combination_term_add",
        "structural-native:model-insert-direct-linear-load-combination-term.v1",
        "direct_linear_load_combination_term_insert",
        "structural-native:model-delete-direct-linear-load-combination-term.v1",
        "direct_linear_load_combination_term_delete",
        "structural-native:model-reorder-direct-linear-load-combination-term.v1",
        "direct_linear_load_combination_term_reorder",
        "structural-native:model-add-nested-linear-load-combination-term.v1",
        "nested_linear_load_combination_term_add",
        "structural-native:model-insert-nested-linear-load-combination-term.v1",
        "nested_linear_load_combination_term_insert",
        "structural-native:model-delete-nested-linear-load-combination-term.v1",
        "nested_linear_load_combination_term_delete",
        "structural-native:model-reorder-nested-linear-load-combination-term.v1",
        "nested_linear_load_combination_term_reorder",
        "structural-native:model-edit-nested-linear-load-combination-factor.v1",
        "nested_linear_load_combination_factor_edit",
        "structural-native:model-edit-nested-linear-load-combination-reference.v1",
        "nested_linear_load_combination_reference_edit",
        "structural-native:model-delete-linear-load-combination.v1",
        "structural-native:model-delete-direct-linear-load-combination.v2",
        "structural-native:model-delete-nested-linear-load-combination.v3",
        "nested_linear_load_combination_delete",
        "structural-native:model-delete-linear-load-pattern.v1",
        "structural-native:model-add-linear-material.v1",
        "structural-native:model-delete-linear-material.v1",
        "structural-native:model-add-frame-section.v1",
        "structural-native:model-delete-frame-section.v1",
        "structural-native:model-add-truss-section.v1",
        "structural-native:model-delete-truss-section.v1",
        "structural-native:upstream-provenance",
        "structural-native-model-editor",
        "edit_model_nodal_load_components",
        "edit_model_constraint_value",
        "edit_model_linear_material",
        "edit_model_frame_section",
        "edit_model_truss_section",
        "edit_model_frame_element_orientation",
        "edit_model_frame_element_properties",
        "edit_model_truss_element_properties",
        "edit_model_element_connectivity",
        "add_model_node",
        "delete_model_orphan_node",
        "add_model_frame3d_member",
        "delete_model_frame3d_leaf_member",
        "delete_model_truss3d_leaf_member",
        "delete_model_frame_section",
        "delete_model_truss_section",
        "add_model_nodal_load",
        "add_model_fixed_constraint",
        "delete_model_fixed_constraint",
        "add_model_linear_load_pattern",
        "add_model_linear_load_combination",
        "delete_model_linear_load_combination",
        "add_model_linear_material",
        "add_model_frame_section",
        "validate_model_bytes",
        "workbench_model_edit_no_change",
        "workbench_model_edit_semantics_invalid",
        "bounded_cpp_revalidated_modelir_node_coordinate_edit",
        "bounded_cpp_revalidated_modelir_contiguous_neutral_node_addition",
        "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_orphan_node_deletion",
        "bounded_cpp_revalidated_existing_modelir_nodal_load_component_edit",
        "bounded_cpp_revalidated_existing_modelir_restrained_dof_prescribed_value_edit",
        "bounded_cpp_revalidated_existing_modelir_linear_elastic_isotropic_material_parameter_edit",
        "bounded_cpp_revalidated_existing_modelir_frame3d_section_parameter_edit",
        "bounded_cpp_revalidated_existing_modelir_truss3d_section_area_edit",
        "bounded_cpp_revalidated_existing_modelir_frame3d_element_local_axis_rotation_edit",
        "bounded_cpp_revalidated_existing_modelir_truss3d_element_material_and_section_reference_edit",
        "bounded_cpp_revalidated_existing_modelir_two_node_element_connectivity_edit",
        "bounded_cpp_revalidated_modelir_linear_frame3d_node_and_member_addition",
        "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_euler_bernoulli_frame3d_leaf_member_and_orphan_node_deletion",
        "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_linear_truss3d_leaf_member_and_orphan_node_deletion",
        "bounded_cpp_revalidated_modelir_linear_static_nodal_load_addition",
        "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_nonzero_six_component_nodal_load_deletion",
        "bounded_cpp_revalidated_modelir_homogeneous_six_dof_fixed_constraint_addition",
        "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_homogeneous_six_dof_fixed_constraint_deletion",
        "bounded_cpp_revalidated_modelir_linear_static_pattern_with_first_nonzero_nodal_load_addition",
        "bounded_cpp_revalidated_two_distinct_existing_linear_static_load_pattern_term_linear_combination_addition",
        "bounded_cpp_revalidated_two_to_64_unique_direct_existing_linear_static_load_pattern_term_linear_combination_addition",
        "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_two_distinct_linear_static_load_pattern_term_linear_combination_deletion",
        "bounded_cpp_revalidated_modelir_linear_elastic_isotropic_material_addition",
        "bounded_cpp_revalidated_modelir_frame3d_section_addition",
        "bounded_cpp_revalidated_last_contiguous_neutral_unreferenced_v1_truss3d_section_deletion",
    ),
    "native/crates/structural-workbench/src/analysis_request.rs": (
        "structural-native-model-linear-request-create-receipt.v1",
        "structural-native-model-linear-combination-request-create-receipt.v1",
        "structural-native-model-linear-direct-combination-request-create-receipt.v2",
        "create_model_linear_analysis_request",
        "create_model_linear_combination_analysis_request",
        "build_model_ir_linear_analysis_request_v1",
        "validate_model_ir_linear_analysis_compatibility",
        "cpp_linear_assembly_preflight_verified",
        "bounded_cpp_assembly_preflighted_modelir_linear_cpu_request_creation",
    ),
    "native/crates/structural-workbench/src/main.rs": (
        'Some("model-view")',
        'Some("model-edit-node")',
        'Some("model-add-node")',
        'Some("model-delete-orphan-node")',
        'Some("model-edit-nodal-load")',
        'Some("model-edit-nodal-load-target")',
        'Some("model-edit-constraint-target")',
        'Some("model-delete-fixed-constraint-dof")',
        'Some("model-edit-constraint-value")',
        'Some("model-edit-linear-material")',
        'Some("model-edit-linear-material-identity")',
        'Some("model-edit-frame-section-identity")',
        'Some("model-edit-frame-section")',
        'Some("model-edit-truss-section")',
        'Some("model-edit-frame-element-orientation")',
        'Some("model-edit-frame-element-properties")',
        'Some("model-edit-truss-element-properties")',
        'Some("model-edit-element-connectivity")',
        'Some("model-add-frame3d-member")',
        'Some("model-add-truss3d-member")',
        'Some("model-delete-frame3d-leaf-member")',
        'Some("model-delete-truss3d-leaf-member")',
        'Some("model-add-nodal-load")',
        'Some("model-delete-nodal-load")',
        'Some("model-add-fixed-constraint")',
        'Some("model-delete-fixed-constraint")',
        'Some("model-add-linear-load-pattern")',
        'Some("model-add-linear-load-combination")',
        'Some("model-edit-linear-load-combination-factor")',
        'Some("model-edit-linear-load-combination-reference")',
        'Some("model-add-linear-load-combination-term")',
        'Some("model-insert-linear-load-combination-term")',
        'Some("model-delete-linear-load-combination-term")',
        'Some("model-add-nested-linear-load-combination-term")',
        'Some("model-insert-nested-linear-load-combination-term")',
        'Some("model-edit-nested-linear-load-combination-factor")',
        'Some("model-edit-nested-linear-load-combination-reference")',
        'Some("model-delete-linear-load-combination")',
        'Some("model-delete-linear-load-pattern")',
        'Some("model-add-linear-material")',
        'Some("model-delete-linear-material")',
        'Some("model-add-frame-section")',
        'Some("model-delete-frame-section")',
        'Some("model-add-truss-section")',
        'Some("model-delete-truss-section")',
        'Some("model-create-linear-analysis-request")',
        'Some("import")',
        'Some("import-mgt")',
        'Some("import-mgt-model-linear")',
        'Some("validate")',
        'Some("run")',
        'Some("resume")',
        'Some("compare")',
        'Some("report")',
        'Some("report-view")',
        'Some("result-view")',
        'Some("result-deformed-view")',
        'Some("report-export-pdf")',
        'Some("interactive")',
        'Some("workflow")',
        'Some("workflow-mgt")',
        'Some("workflow-mgt-model-linear")',
        'Some("inspect")',
        'Some("review")',
        'Some("review-show")',
        'Some("export")',
    ),
    "native/crates/structural-workbench/tests/native_workbench_e2e.rs": (
        "clean_process_restart_workflow_recovers_and_is_bitwise_deterministic",
        "command.env_clear()",
        "restore pre-run durable session",
        "assert_eq!(files.len(), 29)",
        "invalid_transition_and_import_tamper_fail_closed",
        "mgt_import_restart_workflow_preserves_health_and_is_bitwise_deterministic",
        "blocked_mgt_health_cannot_create_an_analysis_workspace",
        "assert_eq!(files.len(), 34)",
        "native_review_inspect_and_export_are_deterministic_and_tamper_evident",
        "localized_linear_report_view_is_utf8_deterministic_and_hash_bound",
        "ndtha_response_view_is_windowed_deterministic_hash_bound_and_terminal_gated",
        "fixed_guided_deformed_view_is_profile_bound_deterministic_and_terminal_gated",
        "localized_pdf_export_is_deterministic_hash_bound_and_non_mutating",
        "general_modelir_topology_view_is_cpp_verified_deterministic_and_fail_closed",
        "node_coordinate_edit_is_provenance_bound_cpp_revalidated_and_create_new",
        "node_coordinate_edit_preserves_analysis_blockers_without_promotion",
        "node_add_is_deterministic_fail_closed_composable_and_cpu_executable",
        "orphan_node_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable",
        "nodal_load_edit_is_provenance_bound_cpp_revalidated_and_create_new",
        "nodal_load_edit_preserves_analysis_blockers_without_promotion",
        "nodal_load_target_edit_is_deterministic_cpp_revalidated_restartable_and_executable",
        "constraint_target_edit_is_deterministic_cpp_revalidated_restartable_and_executable",
        "fixed_constraint_dof_deletion_is_deterministic_restartable_and_cpu_executable",
        "fixed_constraint_dof_addition_is_deterministic_restartable_and_cpu_executable",
        "constraint_value_edit_is_provenance_bound_cpp_revalidated_and_create_new",
        "constraint_value_edit_preserves_source_analysis_blockers_without_promotion",
        "linear_material_edit_is_provenance_bound_cpp_revalidated_and_create_new",
        "frame_section_edit_is_provenance_bound_cpp_revalidated_and_create_new",
        "frame_element_orientation_edit_is_deterministic_fail_closed_and_preserves_blockers",
        "frame_element_properties_edit_is_deterministic_executable_and_fail_closed",
        "element_connectivity_edit_is_deterministic_cpp_revalidated_and_preserves_blockers",
        "frame3d_member_add_is_deterministic_cpp_revalidated_and_linear_executable",
        "nodal_load_add_is_deterministic_cpp_revalidated_and_changes_linear_execution",
        "nodal_load_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable",
        "fixed_constraint_add_is_deterministic_cpp_revalidated_and_changes_linear_execution",
        "fixed_constraint_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable",
        "linear_load_pattern_add_is_atomic_deterministic_cpp_revalidated_and_executable",
        "linear_load_combination_add_is_deterministic_cpp_revalidated_and_cpu_executable",
        "direct_three_pattern_linear_load_combination_executes_and_restarts_without_fallback",
        "direct_linear_load_combination_factor_edit_executes_and_restarts_without_fallback",
        "direct_linear_load_combination_reference_edit_executes_and_restarts_without_fallback",
        "direct_linear_load_combination_term_add_executes_and_restarts_without_fallback",
        "direct_linear_load_combination_term_insert_executes_and_restarts_without_fallback",
        "direct_linear_load_combination_term_delete_executes_and_restarts_without_fallback",
        "direct_linear_load_combination_term_reorder_executes_and_restarts_without_fallback",
        "nested_linear_load_combination_term_add_executes_and_restarts_without_fallback",
        "nested_linear_load_combination_term_insert_executes_and_restarts_without_fallback",
        "nested_linear_load_combination_term_delete_executes_and_restarts_without_fallback",
        "nested_linear_load_combination_term_reorder_executes_and_restarts_without_fallback",
        "nested_linear_load_combination_is_authored_executed_and_restarted_without_fallback",
        "nested_linear_load_combination_factor_edit_executes_and_restarts_without_fallback",
        "nested_linear_load_combination_reference_edit_executes_and_restarts_without_fallback",
        "linear_load_combination_deletion_is_deterministic_fail_closed_and_restores_cpu_execution",
        "linear_material_add_is_deterministic_cpp_revalidated_and_used_by_member_execution",
        "frame_section_add_is_deterministic_cpp_revalidated_and_used_by_member_execution",
        "truss3d_authoring_is_deterministic_fail_closed_restartable_and_cpu_executable",
        "truss3d_edits_are_deterministic_fail_closed_restartable_and_cpu_executable",
        "frame3d_leaf_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable",
        "truss3d_leaf_deletion_is_deterministic_fail_closed_restartable_and_cpu_executable",
        "model_linear_request_creation_is_deterministic_cpp_preflighted_and_product_executable",
        "material_and_section_edits_preserve_blockers_and_degrade_only_matching_roundtrip_rows",
        "workbench_review_exists",
        'view["human_review"]["automatically_inferred"]',
        "sha256:f59193c725e236e4d824b9f2422befce5205050677489e6fc13bb8a31d580ceb",
        "sha256:35f2bebb41411b31cba9e0c395ba74f914097498e8da63e4b14d72704f06c197",
    ),
    "native/crates/structural-workbench/tests/model_ir_linear_workbench_e2e.rs": (
        "clean_environment_mgt_linear_workflow_preserves_import_health_and_restart_identity",
        "simulate MGT linear process death",
        "workbench_mgt_import_binding_mismatch",
    ),
    "docs/native/rust-native-workbench-v1.md": (
        "Import` strictly parses",
        "Rust -> C ABI -> C++",
        "process died while replacing the session file",
        "original MGT bytes",
        "does not yet replace all React/TypeScript UI behavior",
        "explicit human review and handoff export",
        "UTF-8 linear report view",
        "bounded NDTHA response-history view",
        "fixed-guided deformed-shape view",
        "embedded-font PDF export",
        "general ModelIR terminal topology view",
        "provenance-bound ModelIR node-coordinate edit",
        "nodal-load edit",
        "constraint-value editor",
        "linear-material editor",
        "frame-section",
        "frame-element orientation",
        "truss-section area",
        "truss element's compatible",
        "frame3d leaf deleter",
        "truss3d leaf deleter",
        "frame3d-member creator",
        "nodal-load creator",
        "does not infer the human decision",
        "HIP C2",
        "C6",
    ),
    "docs/native/localized-terminal-result-views-v1.md": (
        "en-US",
        "ko-KR",
        "Omitting `--locale` preserves the original `en-US` bytes",
        "append-only distribution v12 receipt",
        "not WCAG conformance",
    ),
    "docs/native/localized-modelir-topology-view-v1.md": (
        "en-US",
        "ko-KR",
        "Omitting `--locale` preserves the original `en-US` bytes exactly",
        "append-only distribution v13 receipt",
        "not general localization",
    ),
    "docs/native/modelir-nodal-load-edit-v1.md": (
        "model-edit-nodal-load",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-nodal-load.v1",
        "load_pattern",
        "all-zero invalid load pattern",
        "C6 remain open",
    ),
    "docs/native/modelir-nodal-load-target-edit-v1.md": (
        "model-edit-nodal-load-target",
        "single C ABI into C++",
        "structural-native:model-edit-nodal-load-target.v1",
        "nodal_load_target",
        "append-only v61",
        "[0,0,0,0,0,0,0,-10000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6 remain open",
    ),
    "docs/native/modelir-constraint-target-edit-v1.md": (
        "model-edit-constraint-target",
        "single C ABI into C++",
        "structural-native:model-edit-constraint-target.v1",
        "constraint_target",
        "append-only v62",
        "[12,13,14,15,16,17]",
        "[0,-1000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6 remain open",
    ),
    "docs/native/modelir-fixed-constraint-dof-deletion-v1.md": (
        "model-delete-fixed-constraint-dof",
        "single C ABI into C++",
        "structural-native:model-delete-fixed-constraint-dof.v1",
        "fixed_constraint_dof_delete",
        "append-only v63",
        "[11,12,13,14,15,16,17]",
        "[0,0,-1000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6 remain open",
    ),
    "docs/native/modelir-fixed-constraint-dof-addition-v1.md": (
        "model-add-fixed-constraint-dof",
        "single C ABI into C++",
        "structural-native:model-add-fixed-constraint-dof.v1",
        "fixed_constraint_dof_add",
        "append-only v64",
        "[12,13,14,15,16,17]",
        "[0,-1000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6 remain open",
    ),
    "docs/native/modelir-fixed-constraint-dof-reorder-v1.md": (
        "model-reorder-fixed-constraint-dof",
        "single C ABI into C++",
        "structural-native:model-reorder-fixed-constraint-dof.v1",
        "fixed_constraint_dof_reorder",
        "append-only v65",
        "[12,13,14,15,16,17]",
        "[0,-1000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6 remain open",
    ),
    "docs/native/modelir-fixed-constraint-identity-edit-v1.md": (
        "model-edit-fixed-constraint-identity",
        "single C ABI into C++",
        "structural-native:model-edit-fixed-constraint-identity.v1",
        "fixed_constraint_identity_edit",
        "append-only v66",
        "[12,13,14,15,16,17]",
        "[0,-1000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "authorize C6",
    ),
    "docs/native/modelir-nodal-load-identity-edit-v1.md": (
        "model-edit-nodal-load-identity",
        "single C ABI into C++",
        "structural-native:model-edit-nodal-load-identity.v1",
        "nodal_load_identity_edit",
        "append-only v67",
        "[12,13,14,15,16,17]",
        "[0,-1000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "authorize C6",
    ),
    "docs/native/modelir-linear-load-pattern-identity-edit-v1.md": (
        "model-edit-linear-load-pattern-identity",
        "single C ABI into C++",
        "structural-native:model-edit-linear-load-pattern-identity.v1",
        "linear_load_pattern_identity_edit",
        "append-only v68",
        "[12,13,14,15,16,17]",
        "[0,-1000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "authorize C6",
    ),
    "docs/native/modelir-linear-material-identity-edit-v1.md": (
        "model-edit-linear-material-identity",
        "single C ABI into C++",
        "structural-native:model-edit-linear-material-identity.v1",
        "linear_material_identity_edit",
        "append-only v69",
        "[6,7,8,9,10,11]",
        "[0,-10000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "authorize C6",
    ),
    "docs/native/modelir-frame-section-identity-edit-v1.md": (
        "model-edit-frame-section-identity",
        "single C ABI into C++",
        "structural-native:model-edit-frame-section-identity.v1",
        "frame_section_identity_edit",
        "append-only v70",
        "[6,7,8,9,10,11]",
        "[0,-10000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "authorize C6",
    ),
    "docs/native/modelir-node-add-v1.md": (
        "model-add-node",
        "Rust -> C ABI -> C++",
        "structural-native:model-add-node.v1",
        "next contiguous index",
        "round-trip",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-orphan-node-delete-v1.md": (
        "model-delete-orphan-node",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-orphan-node.v1",
        "last contiguous neutral orphan node",
        "round-trip",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-constraint-value-edit-v1.md": (
        "model-edit-constraint-value",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-constraint-value.v1",
        "implicit previous value of zero",
        "C6 remain open",
    ),
    "docs/native/modelir-linear-material-edit-v1.md": (
        "model-edit-linear-material",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-linear-material.v1",
        "linear_elastic_isotropic",
        "material` round-trip row",
        "C6 remain open",
    ),
    "docs/native/modelir-frame-section-edit-v1.md": (
        "model-edit-frame-section",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-frame-section.v1",
        "frame_3d",
        "section` round-trip row",
        "C6 remain open",
    ),
    "docs/native/modelir-frame-element-orientation-edit-v1.md": (
        "model-edit-frame-element-orientation",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-frame-element-orientation.v1",
        "frame_3d",
        "element` round-trip row",
        "C6 remain open",
    ),
    "docs/native/modelir-frame-element-properties-edit-v1.md": (
        "model-edit-frame-element-properties",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-frame-element-properties.v1",
        "linear_elastic_isotropic",
        "active external load",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-element-connectivity-edit-v1.md": (
        "model-edit-element-connectivity",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-element-connectivity.v1",
        "two-node",
        "element` round-trip row",
        "C6 remain open",
    ),
    "docs/native/modelir-linear-analysis-request-create-v1.md": (
        "model-create-linear-analysis-request",
        "Rust -> C ABI -> C++",
        "structural-model-ir-linear-analysis-request.v1",
        "ABI v1.13",
        "C6 remain open",
    ),
    "docs/native/modelir-frame3d-member-add-v1.md": (
        "model-add-frame3d-member",
        "Rust -> C ABI -> C++",
        "structural-native:model-add-frame3d-member.v1",
        "euler_bernoulli_3d",
        "typed ResultIR",
        "recovery in the product E2E",
        "C6",
    ),
    "docs/native/modelir-nodal-load-add-v1.md": (
        "model-add-nodal-load",
        "Rust -> C ABI -> C++",
        "structural-native:model-add-nodal-load.v1",
        "linear_static",
        "Typed recovery",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-fixed-constraint-add-v1.md": (
        "model-add-fixed-constraint",
        "Rust -> C ABI -> C++",
        "structural-native:model-add-fixed-constraint.v1",
        "fixed_dofs",
        "active_dof_indices",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-fixed-constraint-deletion-v1.md": (
        "model-delete-fixed-constraint",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-fixed-constraint.v1",
        "last contiguous",
        "one-real-iteration",
        "typed frame recovery",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-nodal-load-deletion-v1.md": (
        "model-delete-nodal-load",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-nodal-load.v1",
        "last contiguous",
        "another nonzero nodal load",
        "one-real-iteration",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-linear-load-pattern-add-v1.md": (
        "model-add-linear-load-pattern",
        "Rust -> C ABI -> C++",
        "structural-native:model-add-linear-load-pattern.v1",
        "linear_static",
        "active_external_load",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-linear-load-combination-add-v1.md": (
        "model-add-linear-load-combination",
        "single C ABI",
        "structural-native:model-add-linear-load-combination.v1",
        "two distinct",
        "--load-combination",
        "structural-native-model-linear-combination-request-create-receipt.v1",
        "active external load",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-linear-load-combination-execution-v1.md": (
        "load-case selector",
        "exactly two terms",
        "structural-native-model-linear-combination-request-create-receipt.v1",
        "Installed CPU static/shared distribution E2E v44",
        "fallback is zero",
        "C6",
    ),
    "docs/native/modelir-direct-linear-load-combination-v1.md": (
        "two through 64",
        "structural-native:model-add-direct-linear-load-combination.v2",
        "structural-native-model-linear-direct-combination-request-create-receipt.v2",
        "frozen ABI v1.13",
        "Installed CPU static/shared distribution E2E v45",
        "[25000,-12000,5000,0,0,0]",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-direct-linear-load-combination-factor-edit-v1.md": (
        "model-edit-linear-load-combination-factor",
        "two through 64 ordered",
        "single C ABI into C++",
        "structural-native:model-edit-direct-linear-load-combination-factor.v1",
        "direct_linear_load_combination_factor_edit",
        "Installed CPU static/shared distribution E2E v49",
        "[25000,-13500,5000,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-direct-linear-load-combination-reference-edit-v1.md": (
        "model-edit-linear-load-combination-reference",
        "two through 64 ordered",
        "single C ABI into C++",
        "structural-native:model-edit-direct-linear-load-combination-reference.v1",
        "direct_linear_load_combination_reference_edit",
        "append-only v51",
        "[120000,0,5000,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-direct-linear-load-combination-deletion-v1.md": (
        "model-delete-linear-load-combination",
        "two through 64",
        "Exact-two",
        "structural-native:model-delete-direct-linear-load-combination.v2",
        "direct_linear_load_combination_delete",
        "Installed CPU static/shared distribution E2E v47",
        "[0,-10000,0,0,0,0]",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-nested-linear-load-combination-v1.md": (
        "model-add-nested-linear-load-combination",
        "root-inclusive combination depth is at most eight",
        "structural-native:model-add-nested-linear-load-combination.v3",
        "structural-native-model-linear-nested-combination-request-create-receipt.v3",
        "frozen ABI v1.13",
        "Installed CPU static/shared distribution E2E v46",
        "[25000,-6000,2500,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-nested-linear-load-combination-factor-edit-v1.md": (
        "model-edit-nested-linear-load-combination-factor",
        "root-inclusive depth at most eight",
        "single C ABI into C++",
        "structural-native:model-edit-nested-linear-load-combination-factor.v1",
        "nested_linear_load_combination_factor_edit",
        "Installed CPU static/shared distribution E2E v50",
        "[25000,-9000,3750,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-nested-linear-load-combination-reference-edit-v1.md": (
        "model-edit-nested-linear-load-combination-reference",
        "root-inclusive depth at most eight",
        "single C ABI into C++",
        "structural-native:model-edit-nested-linear-load-combination-reference.v1",
        "nested_linear_load_combination_reference_edit",
        "append-only v52",
        "[0,-8000,2000,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-direct-linear-load-combination-term-add-v1.md": (
        "model-add-linear-load-combination-term",
        "two through 63",
        "single C ABI into C++",
        "structural-native:model-add-direct-linear-load-combination-term.v1",
        "direct_linear_load_combination_term_add",
        "append-only v53",
        "[25000,-12000,5000,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-direct-linear-load-combination-term-insert-v1.md": (
        "model-insert-linear-load-combination-term",
        "two through 63",
        "single C ABI into C++",
        "structural-native:model-insert-direct-linear-load-combination-term.v1",
        "direct_linear_load_combination_term_insert",
        "append-only v59",
        "[25000,-12000,5000,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-direct-linear-load-combination-term-delete-v1.md": (
        "model-delete-linear-load-combination-term",
        "three through 64",
        "single C ABI into C++",
        "structural-native:model-delete-direct-linear-load-combination-term.v1",
        "direct_linear_load_combination_term_delete",
        "append-only v54",
        "[25000,-12000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-direct-linear-load-combination-term-reorder-v1.md": (
        "model-reorder-linear-load-combination-term",
        "two through 64",
        "single C ABI into C++",
        "structural-native:model-reorder-direct-linear-load-combination-term.v1",
        "direct_linear_load_combination_term_reorder",
        "append-only v58",
        "[25000,-12000,0,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-nested-linear-load-combination-term-add-v1.md": (
        "model-add-nested-linear-load-combination-term",
        "two through 63",
        "root-inclusive depth at most eight",
        "single C ABI into C++",
        "structural-native:model-add-nested-linear-load-combination-term.v1",
        "nested_linear_load_combination_term_add",
        "append-only v55",
        "[25000,-6000,1500,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-nested-linear-load-combination-term-insert-v1.md": (
        "model-insert-nested-linear-load-combination-term",
        "two through 63",
        "single C ABI into C++",
        "structural-native:model-insert-nested-linear-load-combination-term.v1",
        "nested_linear_load_combination_term_insert",
        "append-only v60",
        "[25000,-6000,1500,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-nested-linear-load-combination-term-delete-v1.md": (
        "model-delete-nested-linear-load-combination-term",
        "three through 64",
        "root-inclusive depth at most eight",
        "single C ABI into C++",
        "structural-native:model-delete-nested-linear-load-combination-term.v1",
        "nested_linear_load_combination_term_delete",
        "append-only v56",
        "[0,-6000,1500,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-nested-linear-load-combination-term-reorder-v1.md": (
        "model-reorder-nested-linear-load-combination-term",
        "two through 64",
        "root-inclusive depth at most eight",
        "single C ABI into C++",
        "structural-native:model-reorder-nested-linear-load-combination-term.v1",
        "nested_linear_load_combination_term_reorder",
        "append-only v57",
        "[0,-6000,1500,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-nested-linear-load-combination-deletion-v1.md": (
        "model-delete-linear-load-combination",
        "two through 64",
        "root-inclusive combination depth is at most eight",
        "structural-native:model-delete-nested-linear-load-combination.v3",
        "nested_linear_load_combination_delete",
        "Installed CPU static/shared distribution E2E v48",
        "[0,-12000,5000,0,0,0]",
        "fallback 0",
        "approved HIP C2",
        "C6",
    ),
    "docs/native/modelir-linear-load-combination-deletion-v1.md": (
        "model-delete-linear-load-combination",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-linear-load-combination.v1",
        "last contiguous",
        "two distinct",
        "checkpoint/restart",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-linear-load-pattern-deletion-v1.md": (
        "model-delete-linear-load-pattern",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-linear-load-pattern.v1",
        "last contiguous",
        "load-combination",
        "construction-stage",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-linear-material-add-v1.md": (
        "model-add-linear-material",
        "Rust -> C ABI -> C++",
        "structural-native:model-add-linear-material.v1",
        "linear_elastic_isotropic",
        "state_update_epoch",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-linear-material-deletion-v1.md": (
        "model-delete-linear-material",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-linear-material.v1",
        "last contiguous",
        "steel_material_id",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-frame-section-add-v1.md": (
        "model-add-frame-section",
        "Rust -> C ABI -> C++",
        "structural-native:model-add-frame-section.v1",
        "frame_3d",
        "active external load",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-frame-section-deletion-v1.md": (
        "model-delete-frame-section",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-frame-section.v1",
        "last contiguous",
        "section_id",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-truss-section-deletion-v1.md": (
        "model-delete-truss-section",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-truss-section.v1",
        "last contiguous",
        "section_id",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-truss3d-authoring-v1.md": (
        "model-add-truss-section",
        "model-add-truss3d-member",
        "Rust -> C ABI -> C++",
        "structural-native:model-add-truss-section.v1",
        "structural-native:model-add-truss3d-member.v1",
        "linear_truss_3d",
        "one-real-iteration checkpoint",
        "typed frame-plus-truss recovery",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-truss3d-editing-v1.md": (
        "model-edit-truss-section",
        "model-edit-truss-element-properties",
        "Rust -> C ABI -> C++",
        "structural-native:model-edit-truss-section.v1",
        "structural-native:model-edit-truss-element-properties.v1",
        "one-real-iteration checkpoint",
        "typed recovery identities",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-truss3d-leaf-deletion-v1.md": (
        "model-delete-truss3d-leaf-member",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-truss3d-leaf-member.v1",
        "last contiguous",
        "one-real-iteration checkpoint",
        "frame-only",
        "typed recovery",
        "fallback 0",
        "C6",
    ),
    "docs/native/modelir-frame3d-leaf-deletion-v1.md": (
        "model-delete-frame3d-leaf-member",
        "Rust -> C ABI -> C++",
        "structural-native:model-delete-frame3d-leaf-member.v1",
        "last contiguous",
        "one-real-iteration checkpoint",
        "frame-only typed recovery",
        "fallback 0",
        "C6",
    ),
}


def check_native_workbench(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    member_add_row: dict[str, object] = {}
    load_add_row: dict[str, object] = {}
    load_deletion_row: dict[str, object] = {}
    constraint_add_row: dict[str, object] = {}
    constraint_deletion_row: dict[str, object] = {}
    load_pattern_add_row: dict[str, object] = {}
    load_pattern_deletion_row: dict[str, object] = {}
    material_add_row: dict[str, object] = {}
    material_deletion_row: dict[str, object] = {}
    section_add_row: dict[str, object] = {}
    truss_authoring_row: dict[str, object] = {}
    truss_editing_row: dict[str, object] = {}
    frame_leaf_deletion_row: dict[str, object] = {}
    truss_leaf_deletion_row: dict[str, object] = {}
    property_edit_row: dict[str, object] = {}
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["native_workbench"]
        member_add_row = payload["capabilities"]["modelir_frame3d_member_add"]
        load_add_row = payload["capabilities"]["modelir_nodal_load_add"]
        load_deletion_row = payload["capabilities"]["modelir_nodal_load_deletion"]
        constraint_add_row = payload["capabilities"]["modelir_fixed_constraint_add"]
        constraint_deletion_row = payload["capabilities"][
            "modelir_fixed_constraint_deletion"
        ]
        load_pattern_add_row = payload["capabilities"]["modelir_linear_load_pattern_add"]
        load_pattern_deletion_row = payload["capabilities"][
            "modelir_linear_load_pattern_deletion"
        ]
        material_add_row = payload["capabilities"]["modelir_linear_material_add"]
        material_deletion_row = payload["capabilities"][
            "modelir_linear_material_deletion"
        ]
        section_add_row = payload["capabilities"]["modelir_frame_section_add"]
        truss_authoring_row = payload["capabilities"]["modelir_truss3d_authoring"]
        truss_editing_row = payload["capabilities"]["modelir_truss3d_editing"]
        frame_leaf_deletion_row = payload["capabilities"]["modelir_frame3d_leaf_deletion"]
        truss_leaf_deletion_row = payload["capabilities"]["modelir_truss3d_leaf_deletion"]
        property_edit_row = payload["capabilities"]["modelir_frame_element_properties_edit"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"native_workbench_capability_manifest_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("native_workbench_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append("native_workbench_capability_gate_not_c5")
    if row.get("owner") != "structural-workbench":
        blockers.append("native_workbench_capability_owner_invalid")
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if frame_leaf_deletion_row.get(field) != expected:
            blockers.append(
                f"native_workbench_frame_leaf_deletion_capability_invalid:{field}"
            )
    frame_leaf_deletion_claim = str(frame_leaf_deletion_row.get("claim", ""))
    for token in (
        "last contiguous neutral frame_3d/euler_bernoulli_3d member",
        "last contiguous orphan endpoint node",
        "element/load/constraint/construction-stage/unsupported-feature/round-trip reference",
        "local rotation, offsets, releases",
        "single C ABI into C++",
        "frame-only typed recovery",
        "byte-identical restart",
        "fallback 0",
        "general entity or property deletion",
        "HIP C2",
        "C6",
    ):
        if token not in frame_leaf_deletion_claim:
            blockers.append(
                f"native_workbench_frame_leaf_deletion_claim_token_missing:{token}"
            )
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if member_add_row.get(field) != expected:
            blockers.append(f"native_workbench_member_add_capability_invalid:{field}")
    member_add_claim = str(member_add_row.get("claim", ""))
    for token in (
        "one finite-coordinate node",
        "frame_3d/euler_bernoulli_3d",
        "existing v1 linear-elastic material",
        "native CPU linear product",
        "fallback 0",
        "arbitrary topology",
        "HIP C2",
        "C6",
    ):
        if token not in member_add_claim:
            blockers.append(f"native_workbench_member_add_claim_token_missing:{token}")
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if load_add_row.get(field) != expected:
            blockers.append(f"native_workbench_load_add_capability_invalid:{field}")
    load_add_claim = str(load_add_row.get("claim", ""))
    for token in (
        "nonzero finite six-component SI nodal load",
        "existing linear_static pattern",
        "existing node",
        "single C ABI into C++",
        "new N3-UY external load",
        "changed displacement",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in load_add_claim:
            blockers.append(f"native_workbench_load_add_claim_token_missing:{token}")
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if load_deletion_row.get(field) != expected:
            blockers.append(f"native_workbench_load_deletion_capability_invalid:{field}")
    load_deletion_claim = str(load_deletion_row.get("claim", ""))
    for token in (
        "last contiguous neutral nonzero six-component nodal-load row",
        "another nonzero load",
        "unsupported-feature/direct-round-trip ownership",
        "single C ABI into C++",
        "exact retained active load",
        "typed frame recovery",
        "byte-identical restart",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in load_deletion_claim:
            blockers.append(
                f"native_workbench_load_deletion_claim_token_missing:{token}"
            )
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if constraint_add_row.get(field) != expected:
            blockers.append(f"native_workbench_constraint_add_capability_invalid:{field}")
    constraint_add_claim = str(constraint_add_row.get("claim", ""))
    for token in (
        "homogeneous six-DOF fixed_dofs constraint",
        "existing unconstrained node",
        "single C ABI into C++",
        "active DOFs from 12 to 6",
        "changed displacement",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in constraint_add_claim:
            blockers.append(f"native_workbench_constraint_add_claim_token_missing:{token}")
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if constraint_deletion_row.get(field) != expected:
            blockers.append(
                f"native_workbench_constraint_deletion_capability_invalid:{field}"
            )
    constraint_deletion_claim = str(constraint_deletion_row.get("claim", ""))
    for token in (
        "last contiguous neutral homogeneous six-DOF zero fixed_dofs row",
        "construction-stage/unsupported-feature/round-trip reference",
        "removed identity, index, target node, DOF mask, prescribed values",
        "single C ABI into C++",
        "exact active DOFs and loads",
        "typed frame recovery",
        "byte-identical restart",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in constraint_deletion_claim:
            blockers.append(
                f"native_workbench_constraint_deletion_claim_token_missing:{token}"
            )
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if load_pattern_add_row.get(field) != expected:
            blockers.append(f"native_workbench_load_pattern_add_capability_invalid:{field}")
    load_pattern_add_claim = str(load_pattern_add_row.get("claim", ""))
    for token in (
        "zero-self-weight linear_static pattern",
        "globally unique pattern/load identities",
        "single C ABI into C++",
        "exact N2-FX active load",
        "changed displacement",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in load_pattern_add_claim:
            blockers.append(
                f"native_workbench_load_pattern_add_claim_token_missing:{token}"
            )
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if load_pattern_deletion_row.get(field) != expected:
            blockers.append(
                f"native_workbench_load_pattern_deletion_capability_invalid:{field}"
            )
    load_pattern_deletion_claim = str(load_pattern_deletion_row.get("claim", ""))
    for token in (
        "last contiguous neutral zero-self-weight linear_static pattern",
        "load-combination and construction-stage references",
        "unsupported-feature ownership",
        "direct round-trip mappings",
        "single C ABI into C++",
        "exact retained active load",
        "typed frame recovery",
        "byte-identical restart",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in load_pattern_deletion_claim:
            blockers.append(
                f"native_workbench_load_pattern_deletion_claim_token_missing:{token}"
            )
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if material_add_row.get(field) != expected:
            blockers.append(f"native_workbench_material_add_capability_invalid:{field}")
    material_add_claim = str(material_add_row.get("claim", ""))
    for token in (
        "v1 linear_elastic_isotropic material",
        "fixed stateless trial/commit/rollback schema",
        "single C ABI into C++",
        "exact unchanged active load",
        "changed displacement",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in material_add_claim:
            blockers.append(f"native_workbench_material_add_claim_token_missing:{token}")
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if material_deletion_row.get(field) != expected:
            blockers.append(
                f"native_workbench_material_deletion_capability_invalid:{field}"
            )
    material_deletion_claim = str(material_deletion_row.get("claim", ""))
    for token in (
        "last contiguous neutral unreferenced parameter-set-v1 linear_elastic_isotropic material",
        "element material_id references",
        "section steel_material_id or concrete_material_id references",
        "unsupported-feature ownership",
        "direct round-trip mappings",
        "single C ABI into C++",
        "exact retained material and active load",
        "typed frame recovery",
        "byte-identical restart",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in material_deletion_claim:
            blockers.append(
                f"native_workbench_material_deletion_claim_token_missing:{token}"
            )
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if section_add_row.get(field) != expected:
            blockers.append(f"native_workbench_section_add_capability_invalid:{field}")
    section_add_claim = str(section_add_row.get("claim", ""))
    for token in (
        "v1 frame_3d section",
        "six finite positive physical SI parameters",
        "single C ABI into C++",
        "exact unchanged active load",
        "changed displacement",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in section_add_claim:
            blockers.append(f"native_workbench_section_add_claim_token_missing:{token}")
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if truss_authoring_row.get(field) != expected:
            blockers.append(f"native_workbench_truss_authoring_capability_invalid:{field}")
    truss_authoring_claim = str(truss_authoring_row.get("claim", ""))
    for token in (
        "v1 truss_3d section",
        "truss_3d/linear_truss_3d member",
        "single C ABI into C++",
        "typed frame-plus-truss recovery",
        "byte-identical restart",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in truss_authoring_claim:
            blockers.append(f"native_workbench_truss_authoring_claim_token_missing:{token}")
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if truss_editing_row.get(field) != expected:
            blockers.append(f"native_workbench_truss_editing_capability_invalid:{field}")
    truss_editing_claim = str(truss_editing_row.get("claim", ""))
    for token in (
        "existing v1 truss_3d section",
        "existing truss_3d element",
        "linear_elastic_isotropic material and v1 truss_3d section",
        "single C ABI into C++",
        "distinct baseline/section/property displacement",
        "byte-identical restart",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in truss_editing_claim:
            blockers.append(f"native_workbench_truss_editing_claim_token_missing:{token}")
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if truss_leaf_deletion_row.get(field) != expected:
            blockers.append(
                f"native_workbench_truss_leaf_deletion_capability_invalid:{field}"
            )
    truss_leaf_deletion_claim = str(truss_leaf_deletion_row.get("claim", ""))
    for token in (
        "last contiguous neutral truss_3d/linear_truss_3d member",
        "last contiguous orphan endpoint node",
        "element/load/constraint/construction-stage/unsupported-feature/round-trip reference",
        "single C ABI into C++",
        "frame-only typed recovery",
        "byte-identical restart",
        "fallback 0",
        "general entity or property deletion",
        "HIP C2",
        "C6",
    ):
        if token not in truss_leaf_deletion_claim:
            blockers.append(
                f"native_workbench_truss_leaf_deletion_claim_token_missing:{token}"
            )
    for field, expected in (
        ("status", "implemented"),
        ("cutover_gate", "C5"),
        ("owner", "structural-workbench"),
    ):
        if property_edit_row.get(field) != expected:
            blockers.append(f"native_workbench_property_edit_capability_invalid:{field}")
    property_edit_claim = str(property_edit_row.get("claim", ""))
    for token in (
        "material_id and section_id",
        "existing frame_3d element",
        "v1 linear_elastic_isotropic material",
        "v1 frame_3d section",
        "changed recovered displacement",
        "fallback 0",
        "HIP C2",
        "C6",
    ):
        if token not in property_edit_claim:
            blockers.append(f"native_workbench_property_edit_claim_token_missing:{token}")
    claim = str(row.get("claim", ""))
    for token in (
        "Import -> Validate -> Run -> Resume -> Compare -> Report",
        "Inspect -> Report-view -> Result-view -> Result-deformed-view -> Review -> Export",
        "direct Rust product-library calls",
        "MGT",
        "process death after checkpoint publication",
        "no Python, Node, browser, CLI subprocess",
        "never inferred",
        "English/Korean UTF-8 linear report view",
        "English/Korean embedded-font PDF export",
        "general ModelIR terminal topology view",
        "closed `en-US`/`ko-KR` paths",
        "provenance-bound existing-entity editors",
        "node coordinates",
        "nodal loads",
        "prescribed constraint values",
        "v1 linear materials",
        "v1 frame and truss sections",
        "frame orientation",
        "compatible frame and truss element property references",
        "two-node connectivity",
        "model-bound CPU linear request",
        "fixed-constraint creator",
        "model-delete-fixed-constraint",
        "model-delete-nodal-load",
        "linear-load-pattern creator",
        "linear-material creator",
        "frame-section creator",
        "truss3d section/member",
        "model-delete-frame3d-leaf-member",
        "model-delete-truss3d-leaf-member",
        "English/Korean bounded self-hashed NDTHA response-history view",
        "English/Korean exact-profile deformed-shape view",
        "React/TypeScript removal",
        "HIP C2",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"native_workbench_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"native_workbench_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    f"native_workbench_evidence_token_missing:{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-rust-workbench-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": row.get("cutover_gate"),
        "blockers": blockers,
        "claim_boundary": (
            "This validates one bounded terminal-native C5 workflow. It does not prove general "
            "GUI replacement, live external solver execution, protected HIP C2, packaging, or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_native_workbench(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native Rust Workbench contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
