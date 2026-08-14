#!/usr/bin/env python3
"""Validate bounded native distribution E2E receipts without promoting C6."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
V1_EXPECTED_KEYS = {
    "schema_version",
    "backend_profile",
    "linkage",
    "release_id",
    "source_sha256",
    "bundle_manifest_sha256",
    "installed_backend_receipt_sha256",
    "c2_receipt_sha256",
    "approved_device_runner",
    "single_product_abi",
    "python_lookup_count",
    "node_lookup_count",
    "install_passed",
    "update_passed",
    "rollback_passed",
    "package_consumer_passed",
    "workbench_restart_passed",
    "workbench_direct_parity_passed",
    "result_ir_sha256",
    "report_pdf_sha256",
    "fallback_count",
    "authority",
}
V2_MGT_KEYS = {
    "mgt_workbench_restart_passed",
    "mgt_workbench_direct_parity_passed",
    "mgt_source_sha256",
    "mgt_import_health_sha256",
    "mgt_result_ir_sha256",
    "mgt_report_pdf_sha256",
}
V2_EXPECTED_KEYS = V1_EXPECTED_KEYS | V2_MGT_KEYS
V3_WORKBENCH_KEYS = {
    "workbench_operator_surface_passed",
    "workbench_review_decision",
    "workbench_review_sha256",
    "workbench_export_sha256",
    "mgt_workbench_operator_surface_passed",
    "mgt_workbench_review_decision",
    "mgt_workbench_review_sha256",
    "mgt_workbench_export_sha256",
}
V3_EXPECTED_KEYS = V2_EXPECTED_KEYS | V3_WORKBENCH_KEYS
V4_CATALOG_EVIDENCE_KEYS = {
    "workbench_catalog_surface_passed",
    "workbench_catalog_sha256",
    "workbench_evidence_surface_passed",
    "workbench_evidence_sha256",
}
V4_EXPECTED_KEYS = V3_EXPECTED_KEYS | V4_CATALOG_EVIDENCE_KEYS
V5_EVIDENCE_BUILDER_KEYS = {
    "evidence_builder_check_passed",
    "evidence_builder_check_sha256",
    "evidence_builder_build_passed",
    "evidence_builder_build_sha256",
    "evidence_builder_manifest_sha256",
}
V5_EXPECTED_KEYS = V4_EXPECTED_KEYS | V5_EVIDENCE_BUILDER_KEYS
V6_CATALOG_BUILDER_KEYS = {
    "catalog_builder_check_passed",
    "catalog_builder_check_sha256",
    "catalog_builder_build_passed",
    "catalog_builder_build_sha256",
    "catalog_builder_output_sha256",
}
V6_EXPECTED_KEYS = V5_EXPECTED_KEYS | V6_CATALOG_BUILDER_KEYS
V7_LOCALIZED_PDF_KEYS = {
    "workbench_localized_pdf_surface_passed",
    "workbench_localized_pdf_en_us_sha256",
    "workbench_localized_pdf_ko_kr_sha256",
    "workbench_localized_pdf_en_us_receipt_sha256",
    "workbench_localized_pdf_ko_kr_receipt_sha256",
    "localized_report_font_sha256",
    "localized_report_font_license_sha256",
    "localized_report_font_provenance_sha256",
}
V7_EXPECTED_KEYS = V6_EXPECTED_KEYS | V7_LOCALIZED_PDF_KEYS
V8_MODEL_VIEW_KEYS = {
    "workbench_model_view_surface_passed",
    "workbench_model_view_isometric_sha256",
    "workbench_model_view_xy_sha256",
    "workbench_model_view_xz_sha256",
    "workbench_model_view_yz_sha256",
}
V8_EXPECTED_KEYS = V7_EXPECTED_KEYS | V8_MODEL_VIEW_KEYS
V9_MODEL_EDIT_KEYS = {
    "workbench_model_edit_surface_passed",
    "workbench_model_edit_model_sha256",
    "workbench_model_edit_receipt_sha256",
}
V9_EXPECTED_KEYS = V8_EXPECTED_KEYS | V9_MODEL_EDIT_KEYS
V10_RESULT_VIEW_KEYS = {
    "workbench_result_view_surface_passed",
    "workbench_result_view_top_displacement_sha256",
    "workbench_result_view_drift_ratio_sha256",
    "workbench_result_view_base_shear_sha256",
    "workbench_result_view_residual_inf_sha256",
    "workbench_result_view_window_sha256",
}
V10_EXPECTED_KEYS = V9_EXPECTED_KEYS | V10_RESULT_VIEW_KEYS
V11_DEFORMED_VIEW_KEYS = {
    "workbench_deformed_view_surface_passed",
    "workbench_deformed_view_isometric_sha256",
    "workbench_deformed_view_xy_sha256",
    "workbench_deformed_view_xz_sha256",
    "workbench_deformed_view_yz_sha256",
    "workbench_deformed_view_explicit_sha256",
}
V11_EXPECTED_KEYS = V10_EXPECTED_KEYS | V11_DEFORMED_VIEW_KEYS
V12_LOCALIZED_RESULT_VIEW_KEYS = {
    "workbench_localized_result_views_surface_passed",
    "workbench_result_view_ko_kr_sha256",
    "workbench_deformed_view_ko_kr_sha256",
}
V12_EXPECTED_KEYS = V11_EXPECTED_KEYS | V12_LOCALIZED_RESULT_VIEW_KEYS
V13_LOCALIZED_MODEL_VIEW_KEYS = {
    "workbench_localized_model_view_surface_passed",
    "workbench_model_view_ko_kr_sha256",
}
V13_EXPECTED_KEYS = V12_EXPECTED_KEYS | V13_LOCALIZED_MODEL_VIEW_KEYS
V14_MODEL_IR_LINEAR_WORKBENCH_KEYS = {
    "model_ir_linear_workbench_restart_passed",
    "model_ir_linear_workbench_direct_parity_passed",
    "model_ir_linear_workbench_operator_surface_passed",
    "model_ir_linear_workbench_review_decision",
    "model_ir_linear_workbench_review_sha256",
    "model_ir_linear_workbench_export_sha256",
    "model_ir_linear_result_ir_sha256",
    "model_ir_linear_result_recovery_ir_sha256",
    "model_ir_linear_report_pdf_sha256",
    "model_ir_linear_pdf_receipt_sha256",
    "model_ir_linear_report_receipt_sha256",
}
V14_EXPECTED_KEYS = V13_EXPECTED_KEYS | V14_MODEL_IR_LINEAR_WORKBENCH_KEYS
V15_MODEL_IR_LINEAR_LOCALIZED_PDF_KEYS = {
    "model_ir_linear_localized_pdf_surface_passed",
    "model_ir_linear_localized_pdf_en_us_sha256",
    "model_ir_linear_localized_pdf_ko_kr_sha256",
    "model_ir_linear_localized_pdf_en_us_receipt_sha256",
    "model_ir_linear_localized_pdf_ko_kr_receipt_sha256",
}
V15_EXPECTED_KEYS = V14_EXPECTED_KEYS | V15_MODEL_IR_LINEAR_LOCALIZED_PDF_KEYS
V16_MGT_MODEL_IR_LINEAR_WORKBENCH_KEYS = {
    "mgt_model_ir_linear_workbench_restart_passed",
    "mgt_model_ir_linear_workbench_direct_parity_passed",
    "mgt_model_ir_linear_workbench_operator_surface_passed",
    "mgt_model_ir_linear_workbench_review_decision",
    "mgt_model_ir_linear_workbench_review_sha256",
    "mgt_model_ir_linear_workbench_export_sha256",
    "mgt_model_ir_linear_source_sha256",
    "mgt_model_ir_linear_import_health_sha256",
    "mgt_model_ir_linear_result_ir_sha256",
    "mgt_model_ir_linear_result_recovery_ir_sha256",
    "mgt_model_ir_linear_report_pdf_sha256",
    "mgt_model_ir_linear_pdf_receipt_sha256",
    "mgt_model_ir_linear_report_receipt_sha256",
}
V16_EXPECTED_KEYS = V15_EXPECTED_KEYS | V16_MGT_MODEL_IR_LINEAR_WORKBENCH_KEYS
V17_NODAL_LOAD_EDIT_KEYS = {
    "workbench_nodal_load_edit_surface_passed",
    "workbench_nodal_load_edit_model_sha256",
    "workbench_nodal_load_edit_receipt_sha256",
}
V17_EXPECTED_KEYS = V16_EXPECTED_KEYS | V17_NODAL_LOAD_EDIT_KEYS
V18_CONSTRAINT_VALUE_EDIT_KEYS = {
    "workbench_constraint_value_edit_surface_passed",
    "workbench_constraint_value_edit_model_sha256",
    "workbench_constraint_value_edit_receipt_sha256",
}
V18_EXPECTED_KEYS = V17_EXPECTED_KEYS | V18_CONSTRAINT_VALUE_EDIT_KEYS
V19_PROPERTY_EDIT_KEYS = {
    "workbench_linear_material_edit_surface_passed",
    "workbench_linear_material_edit_model_sha256",
    "workbench_linear_material_edit_receipt_sha256",
    "workbench_frame_section_edit_surface_passed",
    "workbench_frame_section_edit_model_sha256",
    "workbench_frame_section_edit_receipt_sha256",
}
V19_EXPECTED_KEYS = V18_EXPECTED_KEYS | V19_PROPERTY_EDIT_KEYS
V20_FRAME_ELEMENT_ORIENTATION_EDIT_KEYS = {
    "workbench_frame_element_orientation_edit_surface_passed",
    "workbench_frame_element_orientation_edit_model_sha256",
    "workbench_frame_element_orientation_edit_receipt_sha256",
}
V20_EXPECTED_KEYS = V19_EXPECTED_KEYS | V20_FRAME_ELEMENT_ORIENTATION_EDIT_KEYS
V21_ELEMENT_CONNECTIVITY_EDIT_KEYS = {
    "workbench_element_connectivity_edit_surface_passed",
    "workbench_element_connectivity_edit_model_sha256",
    "workbench_element_connectivity_edit_receipt_sha256",
}
V21_EXPECTED_KEYS = V20_EXPECTED_KEYS | V21_ELEMENT_CONNECTIVITY_EDIT_KEYS
V22_MODEL_LINEAR_REQUEST_CREATE_KEYS = {
    "workbench_model_linear_request_create_surface_passed",
    "workbench_model_linear_request_create_request_sha256",
    "workbench_model_linear_request_create_receipt_sha256",
}
V22_EXPECTED_KEYS = V21_EXPECTED_KEYS | V22_MODEL_LINEAR_REQUEST_CREATE_KEYS
V23_FRAME3D_MEMBER_ADD_KEYS = {
    "workbench_frame3d_member_add_surface_passed",
    "workbench_frame3d_member_add_model_sha256",
    "workbench_frame3d_member_add_receipt_sha256",
    "workbench_frame3d_member_add_request_sha256",
    "workbench_frame3d_member_add_result_ir_sha256",
}
V23_EXPECTED_KEYS = V22_EXPECTED_KEYS | V23_FRAME3D_MEMBER_ADD_KEYS
V24_NODAL_LOAD_ADD_KEYS = {
    "workbench_nodal_load_add_surface_passed",
    "workbench_nodal_load_add_model_sha256",
    "workbench_nodal_load_add_receipt_sha256",
    "workbench_nodal_load_add_request_sha256",
    "workbench_nodal_load_add_result_ir_sha256",
    "workbench_nodal_load_add_recovery_sha256",
}
V24_EXPECTED_KEYS = V23_EXPECTED_KEYS | V24_NODAL_LOAD_ADD_KEYS
V25_FIXED_CONSTRAINT_ADD_KEYS = {
    "workbench_fixed_constraint_add_surface_passed",
    "workbench_fixed_constraint_add_model_sha256",
    "workbench_fixed_constraint_add_receipt_sha256",
    "workbench_fixed_constraint_add_request_sha256",
    "workbench_fixed_constraint_add_result_ir_sha256",
    "workbench_fixed_constraint_add_recovery_sha256",
}
V25_EXPECTED_KEYS = V24_EXPECTED_KEYS | V25_FIXED_CONSTRAINT_ADD_KEYS
V26_LINEAR_LOAD_PATTERN_ADD_KEYS = {
    "workbench_linear_load_pattern_add_surface_passed",
    "workbench_linear_load_pattern_add_model_sha256",
    "workbench_linear_load_pattern_add_receipt_sha256",
    "workbench_linear_load_pattern_add_request_sha256",
    "workbench_linear_load_pattern_add_result_ir_sha256",
    "workbench_linear_load_pattern_add_recovery_sha256",
}
V26_EXPECTED_KEYS = V25_EXPECTED_KEYS | V26_LINEAR_LOAD_PATTERN_ADD_KEYS
V27_LINEAR_MATERIAL_ADD_KEYS = {
    "workbench_linear_material_add_surface_passed",
    "workbench_linear_material_add_model_sha256",
    "workbench_linear_material_add_receipt_sha256",
    "workbench_linear_material_add_composed_model_sha256",
    "workbench_linear_material_add_request_sha256",
    "workbench_linear_material_add_result_ir_sha256",
    "workbench_linear_material_add_recovery_sha256",
}
V27_EXPECTED_KEYS = V26_EXPECTED_KEYS | V27_LINEAR_MATERIAL_ADD_KEYS
V28_FRAME_SECTION_ADD_KEYS = {
    "workbench_frame_section_add_surface_passed",
    "workbench_frame_section_add_model_sha256",
    "workbench_frame_section_add_receipt_sha256",
    "workbench_frame_section_add_composed_model_sha256",
    "workbench_frame_section_add_request_sha256",
    "workbench_frame_section_add_result_ir_sha256",
    "workbench_frame_section_add_recovery_sha256",
}
V28_EXPECTED_KEYS = V27_EXPECTED_KEYS | V28_FRAME_SECTION_ADD_KEYS
V29_FRAME_ELEMENT_PROPERTIES_EDIT_KEYS = {
    "workbench_frame_element_properties_edit_surface_passed",
    "workbench_frame_element_properties_edit_model_sha256",
    "workbench_frame_element_properties_edit_receipt_sha256",
    "workbench_frame_element_properties_edit_request_sha256",
    "workbench_frame_element_properties_edit_result_ir_sha256",
    "workbench_frame_element_properties_edit_recovery_sha256",
}
V29_EXPECTED_KEYS = V28_EXPECTED_KEYS | V29_FRAME_ELEMENT_PROPERTIES_EDIT_KEYS
V30_TRUSS3D_AUTHORING_KEYS = {
    "workbench_truss3d_authoring_surface_passed",
    "workbench_truss3d_authoring_section_model_sha256",
    "workbench_truss3d_authoring_section_receipt_sha256",
    "workbench_truss3d_authoring_member_model_sha256",
    "workbench_truss3d_authoring_member_receipt_sha256",
    "workbench_truss3d_authoring_composed_model_sha256",
    "workbench_truss3d_authoring_request_sha256",
    "workbench_truss3d_authoring_result_ir_sha256",
    "workbench_truss3d_authoring_recovery_sha256",
}
V30_EXPECTED_KEYS = V29_EXPECTED_KEYS | V30_TRUSS3D_AUTHORING_KEYS
V31_TRUSS3D_EDITING_KEYS = {
    "workbench_truss3d_editing_surface_passed",
    "workbench_truss3d_editing_section_model_sha256",
    "workbench_truss3d_editing_section_receipt_sha256",
    "workbench_truss3d_editing_properties_model_sha256",
    "workbench_truss3d_editing_properties_receipt_sha256",
    "workbench_truss3d_editing_section_result_ir_sha256",
    "workbench_truss3d_editing_request_sha256",
    "workbench_truss3d_editing_result_ir_sha256",
    "workbench_truss3d_editing_recovery_sha256",
}
V31_EXPECTED_KEYS = V30_EXPECTED_KEYS | V31_TRUSS3D_EDITING_KEYS
V32_TRUSS3D_LEAF_DELETION_KEYS = {
    "workbench_truss3d_leaf_deletion_surface_passed",
    "workbench_truss3d_leaf_deletion_model_sha256",
    "workbench_truss3d_leaf_deletion_receipt_sha256",
    "workbench_truss3d_leaf_deletion_request_sha256",
    "workbench_truss3d_leaf_deletion_result_ir_sha256",
    "workbench_truss3d_leaf_deletion_recovery_sha256",
}
V32_EXPECTED_KEYS = V31_EXPECTED_KEYS | V32_TRUSS3D_LEAF_DELETION_KEYS
V33_FRAME3D_LEAF_DELETION_KEYS = {
    "workbench_frame3d_leaf_deletion_surface_passed",
    "workbench_frame3d_leaf_deletion_model_sha256",
    "workbench_frame3d_leaf_deletion_receipt_sha256",
    "workbench_frame3d_leaf_deletion_request_sha256",
    "workbench_frame3d_leaf_deletion_result_ir_sha256",
    "workbench_frame3d_leaf_deletion_recovery_sha256",
}
V33_EXPECTED_KEYS = V32_EXPECTED_KEYS | V33_FRAME3D_LEAF_DELETION_KEYS
V34_FIXED_CONSTRAINT_DELETE_KEYS = {
    "workbench_fixed_constraint_delete_surface_passed",
    "workbench_fixed_constraint_delete_model_sha256",
    "workbench_fixed_constraint_delete_receipt_sha256",
    "workbench_fixed_constraint_delete_request_sha256",
    "workbench_fixed_constraint_delete_result_ir_sha256",
    "workbench_fixed_constraint_delete_recovery_sha256",
}
V34_EXPECTED_KEYS = V33_EXPECTED_KEYS | V34_FIXED_CONSTRAINT_DELETE_KEYS
V35_NODAL_LOAD_DELETE_KEYS = {
    "workbench_nodal_load_delete_surface_passed",
    "workbench_nodal_load_delete_model_sha256",
    "workbench_nodal_load_delete_receipt_sha256",
    "workbench_nodal_load_delete_request_sha256",
    "workbench_nodal_load_delete_result_ir_sha256",
    "workbench_nodal_load_delete_recovery_sha256",
}
V35_EXPECTED_KEYS = V34_EXPECTED_KEYS | V35_NODAL_LOAD_DELETE_KEYS
V36_LINEAR_LOAD_PATTERN_DELETE_KEYS = {
    "workbench_linear_load_pattern_delete_surface_passed",
    "workbench_linear_load_pattern_delete_model_sha256",
    "workbench_linear_load_pattern_delete_receipt_sha256",
    "workbench_linear_load_pattern_delete_request_sha256",
    "workbench_linear_load_pattern_delete_result_ir_sha256",
    "workbench_linear_load_pattern_delete_recovery_sha256",
}
V36_EXPECTED_KEYS = V35_EXPECTED_KEYS | V36_LINEAR_LOAD_PATTERN_DELETE_KEYS
V37_LINEAR_MATERIAL_DELETE_KEYS = {
    "workbench_linear_material_delete_surface_passed",
    "workbench_linear_material_delete_model_sha256",
    "workbench_linear_material_delete_receipt_sha256",
    "workbench_linear_material_delete_request_sha256",
    "workbench_linear_material_delete_result_ir_sha256",
    "workbench_linear_material_delete_recovery_sha256",
}
V37_EXPECTED_KEYS = V36_EXPECTED_KEYS | V37_LINEAR_MATERIAL_DELETE_KEYS
V38_FRAME_SECTION_DELETE_KEYS = {
    "workbench_frame_section_delete_surface_passed",
    "workbench_frame_section_delete_model_sha256",
    "workbench_frame_section_delete_receipt_sha256",
    "workbench_frame_section_delete_request_sha256",
    "workbench_frame_section_delete_result_ir_sha256",
    "workbench_frame_section_delete_recovery_sha256",
}
V38_EXPECTED_KEYS = V37_EXPECTED_KEYS | V38_FRAME_SECTION_DELETE_KEYS
V39_TRUSS_SECTION_DELETE_KEYS = {
    "workbench_truss_section_delete_surface_passed",
    "workbench_truss_section_delete_model_sha256",
    "workbench_truss_section_delete_receipt_sha256",
    "workbench_truss_section_delete_request_sha256",
    "workbench_truss_section_delete_result_ir_sha256",
    "workbench_truss_section_delete_recovery_sha256",
}
V39_EXPECTED_KEYS = V38_EXPECTED_KEYS | V39_TRUSS_SECTION_DELETE_KEYS
V40_NODE_ADD_KEYS = {
    "workbench_node_add_surface_passed",
    "workbench_node_add_model_sha256",
    "workbench_node_add_receipt_sha256",
    "workbench_node_add_composed_model_sha256",
    "workbench_node_add_request_sha256",
    "workbench_node_add_result_ir_sha256",
    "workbench_node_add_recovery_sha256",
}
V40_EXPECTED_KEYS = V39_EXPECTED_KEYS | V40_NODE_ADD_KEYS
V41_ORPHAN_NODE_DELETE_KEYS = {
    "workbench_orphan_node_delete_surface_passed",
    "workbench_orphan_node_delete_model_sha256",
    "workbench_orphan_node_delete_receipt_sha256",
    "workbench_orphan_node_delete_request_sha256",
    "workbench_orphan_node_delete_result_ir_sha256",
    "workbench_orphan_node_delete_recovery_sha256",
}
V41_EXPECTED_KEYS = V40_EXPECTED_KEYS | V41_ORPHAN_NODE_DELETE_KEYS
V42_LINEAR_LOAD_COMBINATION_ADD_KEYS = {
    "workbench_linear_load_combination_add_surface_passed",
    "workbench_linear_load_combination_add_model_sha256",
    "workbench_linear_load_combination_add_receipt_sha256",
    "workbench_linear_load_combination_add_validation_sha256",
    "workbench_linear_load_combination_add_view_sha256",
    "workbench_linear_load_combination_add_solver_rejection_sha256",
}
V42_EXPECTED_KEYS = V41_EXPECTED_KEYS | V42_LINEAR_LOAD_COMBINATION_ADD_KEYS
V43_LINEAR_LOAD_COMBINATION_DELETE_KEYS = {
    "workbench_linear_load_combination_delete_surface_passed",
    "workbench_linear_load_combination_delete_model_sha256",
    "workbench_linear_load_combination_delete_receipt_sha256",
    "workbench_linear_load_combination_delete_request_sha256",
    "workbench_linear_load_combination_delete_result_ir_sha256",
    "workbench_linear_load_combination_delete_recovery_sha256",
}
V43_EXPECTED_KEYS = V42_EXPECTED_KEYS | V43_LINEAR_LOAD_COMBINATION_DELETE_KEYS
V44_LINEAR_LOAD_COMBINATION_EXECUTION_KEYS = {
    "workbench_linear_load_combination_execution_surface_passed",
    "workbench_linear_load_combination_request_receipt_sha256",
    "workbench_linear_load_combination_request_sha256",
    "workbench_linear_load_combination_assembly_receipt_sha256",
    "workbench_linear_load_combination_checkpoint_sha256",
    "workbench_linear_load_combination_result_ir_sha256",
    "workbench_linear_load_combination_recovery_sha256",
    "workbench_linear_load_combination_report_ir_sha256",
    "workbench_linear_load_combination_restart_passed",
}
V44_EXPECTED_KEYS = V43_EXPECTED_KEYS | V44_LINEAR_LOAD_COMBINATION_EXECUTION_KEYS
V45_DIRECT_LINEAR_LOAD_COMBINATION_KEYS = {
    "workbench_direct_linear_load_combination_surface_passed",
    "workbench_direct_linear_load_combination_model_sha256",
    "workbench_direct_linear_load_combination_edit_receipt_sha256",
    "workbench_direct_linear_load_combination_request_receipt_sha256",
    "workbench_direct_linear_load_combination_request_sha256",
    "workbench_direct_linear_load_combination_assembly_receipt_sha256",
    "workbench_direct_linear_load_combination_checkpoint_sha256",
    "workbench_direct_linear_load_combination_result_ir_sha256",
    "workbench_direct_linear_load_combination_recovery_sha256",
    "workbench_direct_linear_load_combination_report_ir_sha256",
    "workbench_direct_linear_load_combination_restart_passed",
}
V45_EXPECTED_KEYS = V44_EXPECTED_KEYS | V45_DIRECT_LINEAR_LOAD_COMBINATION_KEYS
V46_NESTED_LINEAR_LOAD_COMBINATION_KEYS = {
    "workbench_nested_linear_load_combination_surface_passed",
    "workbench_nested_linear_load_combination_model_sha256",
    "workbench_nested_linear_load_combination_edit_receipt_sha256",
    "workbench_nested_linear_load_combination_request_receipt_sha256",
    "workbench_nested_linear_load_combination_request_sha256",
    "workbench_nested_linear_load_combination_assembly_receipt_sha256",
    "workbench_nested_linear_load_combination_checkpoint_sha256",
    "workbench_nested_linear_load_combination_result_ir_sha256",
    "workbench_nested_linear_load_combination_recovery_sha256",
    "workbench_nested_linear_load_combination_report_ir_sha256",
    "workbench_nested_linear_load_combination_restart_passed",
}
V46_EXPECTED_KEYS = V45_EXPECTED_KEYS | V46_NESTED_LINEAR_LOAD_COMBINATION_KEYS
V47_DIRECT_LINEAR_LOAD_COMBINATION_DELETE_KEYS = {
    "workbench_direct_linear_load_combination_delete_surface_passed",
    "workbench_direct_linear_load_combination_delete_model_sha256",
    "workbench_direct_linear_load_combination_delete_receipt_sha256",
    "workbench_direct_linear_load_combination_delete_request_sha256",
    "workbench_direct_linear_load_combination_delete_assembly_receipt_sha256",
    "workbench_direct_linear_load_combination_delete_checkpoint_sha256",
    "workbench_direct_linear_load_combination_delete_result_ir_sha256",
    "workbench_direct_linear_load_combination_delete_recovery_sha256",
    "workbench_direct_linear_load_combination_delete_report_ir_sha256",
    "workbench_direct_linear_load_combination_delete_restart_passed",
}
V47_EXPECTED_KEYS = V46_EXPECTED_KEYS | V47_DIRECT_LINEAR_LOAD_COMBINATION_DELETE_KEYS
V48_NESTED_LINEAR_LOAD_COMBINATION_DELETE_KEYS = {
    "workbench_nested_linear_load_combination_delete_surface_passed",
    "workbench_nested_linear_load_combination_delete_model_sha256",
    "workbench_nested_linear_load_combination_delete_receipt_sha256",
    "workbench_nested_linear_load_combination_delete_request_receipt_sha256",
    "workbench_nested_linear_load_combination_delete_request_sha256",
    "workbench_nested_linear_load_combination_delete_assembly_receipt_sha256",
    "workbench_nested_linear_load_combination_delete_checkpoint_sha256",
    "workbench_nested_linear_load_combination_delete_result_ir_sha256",
    "workbench_nested_linear_load_combination_delete_recovery_sha256",
    "workbench_nested_linear_load_combination_delete_report_ir_sha256",
    "workbench_nested_linear_load_combination_delete_restart_passed",
}
V48_EXPECTED_KEYS = V47_EXPECTED_KEYS | V48_NESTED_LINEAR_LOAD_COMBINATION_DELETE_KEYS
V49_DIRECT_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_KEYS = {
    "workbench_direct_linear_load_combination_factor_edit_surface_passed",
    "workbench_direct_linear_load_combination_factor_edit_model_sha256",
    "workbench_direct_linear_load_combination_factor_edit_receipt_sha256",
    "workbench_direct_linear_load_combination_factor_edit_request_receipt_sha256",
    "workbench_direct_linear_load_combination_factor_edit_request_sha256",
    "workbench_direct_linear_load_combination_factor_edit_assembly_receipt_sha256",
    "workbench_direct_linear_load_combination_factor_edit_checkpoint_sha256",
    "workbench_direct_linear_load_combination_factor_edit_result_ir_sha256",
    "workbench_direct_linear_load_combination_factor_edit_recovery_sha256",
    "workbench_direct_linear_load_combination_factor_edit_report_ir_sha256",
    "workbench_direct_linear_load_combination_factor_edit_restart_passed",
}
V49_EXPECTED_KEYS = (
    V48_EXPECTED_KEYS | V49_DIRECT_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_KEYS
)
V50_NESTED_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_KEYS = {
    "workbench_nested_linear_load_combination_factor_edit_surface_passed",
    "workbench_nested_linear_load_combination_factor_edit_model_sha256",
    "workbench_nested_linear_load_combination_factor_edit_receipt_sha256",
    "workbench_nested_linear_load_combination_factor_edit_request_receipt_sha256",
    "workbench_nested_linear_load_combination_factor_edit_request_sha256",
    "workbench_nested_linear_load_combination_factor_edit_assembly_receipt_sha256",
    "workbench_nested_linear_load_combination_factor_edit_checkpoint_sha256",
    "workbench_nested_linear_load_combination_factor_edit_result_ir_sha256",
    "workbench_nested_linear_load_combination_factor_edit_recovery_sha256",
    "workbench_nested_linear_load_combination_factor_edit_report_ir_sha256",
    "workbench_nested_linear_load_combination_factor_edit_restart_passed",
}
V50_EXPECTED_KEYS = (
    V49_EXPECTED_KEYS | V50_NESTED_LINEAR_LOAD_COMBINATION_FACTOR_EDIT_KEYS
)
V51_DIRECT_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_KEYS = {
    "workbench_direct_linear_load_combination_reference_edit_surface_passed",
    "workbench_direct_linear_load_combination_reference_edit_model_sha256",
    "workbench_direct_linear_load_combination_reference_edit_receipt_sha256",
    "workbench_direct_linear_load_combination_reference_edit_request_receipt_sha256",
    "workbench_direct_linear_load_combination_reference_edit_request_sha256",
    "workbench_direct_linear_load_combination_reference_edit_assembly_receipt_sha256",
    "workbench_direct_linear_load_combination_reference_edit_checkpoint_sha256",
    "workbench_direct_linear_load_combination_reference_edit_result_ir_sha256",
    "workbench_direct_linear_load_combination_reference_edit_recovery_sha256",
    "workbench_direct_linear_load_combination_reference_edit_report_ir_sha256",
    "workbench_direct_linear_load_combination_reference_edit_restart_passed",
}
V51_EXPECTED_KEYS = (
    V50_EXPECTED_KEYS | V51_DIRECT_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_KEYS
)
V52_NESTED_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_KEYS = {
    "workbench_nested_linear_load_combination_reference_edit_surface_passed",
    "workbench_nested_linear_load_combination_reference_edit_model_sha256",
    "workbench_nested_linear_load_combination_reference_edit_receipt_sha256",
    "workbench_nested_linear_load_combination_reference_edit_request_receipt_sha256",
    "workbench_nested_linear_load_combination_reference_edit_request_sha256",
    "workbench_nested_linear_load_combination_reference_edit_assembly_receipt_sha256",
    "workbench_nested_linear_load_combination_reference_edit_checkpoint_sha256",
    "workbench_nested_linear_load_combination_reference_edit_result_ir_sha256",
    "workbench_nested_linear_load_combination_reference_edit_recovery_sha256",
    "workbench_nested_linear_load_combination_reference_edit_report_ir_sha256",
    "workbench_nested_linear_load_combination_reference_edit_restart_passed",
}
V52_EXPECTED_KEYS = (
    V51_EXPECTED_KEYS | V52_NESTED_LINEAR_LOAD_COMBINATION_REFERENCE_EDIT_KEYS
)
V53_DIRECT_LINEAR_LOAD_COMBINATION_TERM_ADD_KEYS = {
    "workbench_direct_linear_load_combination_term_add_surface_passed",
    "workbench_direct_linear_load_combination_term_add_model_sha256",
    "workbench_direct_linear_load_combination_term_add_receipt_sha256",
    "workbench_direct_linear_load_combination_term_add_request_receipt_sha256",
    "workbench_direct_linear_load_combination_term_add_request_sha256",
    "workbench_direct_linear_load_combination_term_add_assembly_receipt_sha256",
    "workbench_direct_linear_load_combination_term_add_checkpoint_sha256",
    "workbench_direct_linear_load_combination_term_add_result_ir_sha256",
    "workbench_direct_linear_load_combination_term_add_recovery_sha256",
    "workbench_direct_linear_load_combination_term_add_report_ir_sha256",
    "workbench_direct_linear_load_combination_term_add_restart_passed",
}
V53_EXPECTED_KEYS = V52_EXPECTED_KEYS | V53_DIRECT_LINEAR_LOAD_COMBINATION_TERM_ADD_KEYS
V54_DIRECT_LINEAR_LOAD_COMBINATION_TERM_DELETE_KEYS = {
    "workbench_direct_linear_load_combination_term_delete_surface_passed",
    "workbench_direct_linear_load_combination_term_delete_model_sha256",
    "workbench_direct_linear_load_combination_term_delete_receipt_sha256",
    "workbench_direct_linear_load_combination_term_delete_request_receipt_sha256",
    "workbench_direct_linear_load_combination_term_delete_request_sha256",
    "workbench_direct_linear_load_combination_term_delete_assembly_receipt_sha256",
    "workbench_direct_linear_load_combination_term_delete_checkpoint_sha256",
    "workbench_direct_linear_load_combination_term_delete_result_ir_sha256",
    "workbench_direct_linear_load_combination_term_delete_recovery_sha256",
    "workbench_direct_linear_load_combination_term_delete_report_ir_sha256",
    "workbench_direct_linear_load_combination_term_delete_restart_passed",
}
V54_EXPECTED_KEYS = V53_EXPECTED_KEYS | V54_DIRECT_LINEAR_LOAD_COMBINATION_TERM_DELETE_KEYS
V55_NESTED_LINEAR_LOAD_COMBINATION_TERM_ADD_KEYS = {
    "workbench_nested_linear_load_combination_term_add_surface_passed",
    "workbench_nested_linear_load_combination_term_add_model_sha256",
    "workbench_nested_linear_load_combination_term_add_receipt_sha256",
    "workbench_nested_linear_load_combination_term_add_request_receipt_sha256",
    "workbench_nested_linear_load_combination_term_add_request_sha256",
    "workbench_nested_linear_load_combination_term_add_assembly_receipt_sha256",
    "workbench_nested_linear_load_combination_term_add_checkpoint_sha256",
    "workbench_nested_linear_load_combination_term_add_result_ir_sha256",
    "workbench_nested_linear_load_combination_term_add_recovery_sha256",
    "workbench_nested_linear_load_combination_term_add_report_ir_sha256",
    "workbench_nested_linear_load_combination_term_add_restart_passed",
}
V55_EXPECTED_KEYS = V54_EXPECTED_KEYS | V55_NESTED_LINEAR_LOAD_COMBINATION_TERM_ADD_KEYS
V56_NESTED_LINEAR_LOAD_COMBINATION_TERM_DELETE_KEYS = {
    "workbench_nested_linear_load_combination_term_delete_surface_passed",
    "workbench_nested_linear_load_combination_term_delete_model_sha256",
    "workbench_nested_linear_load_combination_term_delete_receipt_sha256",
    "workbench_nested_linear_load_combination_term_delete_request_receipt_sha256",
    "workbench_nested_linear_load_combination_term_delete_request_sha256",
    "workbench_nested_linear_load_combination_term_delete_assembly_receipt_sha256",
    "workbench_nested_linear_load_combination_term_delete_checkpoint_sha256",
    "workbench_nested_linear_load_combination_term_delete_result_ir_sha256",
    "workbench_nested_linear_load_combination_term_delete_recovery_sha256",
    "workbench_nested_linear_load_combination_term_delete_report_ir_sha256",
    "workbench_nested_linear_load_combination_term_delete_restart_passed",
}
V56_EXPECTED_KEYS = V55_EXPECTED_KEYS | V56_NESTED_LINEAR_LOAD_COMBINATION_TERM_DELETE_KEYS
V57_NESTED_LINEAR_LOAD_COMBINATION_TERM_REORDER_KEYS = {
    "workbench_nested_linear_load_combination_term_reorder_surface_passed",
    "workbench_nested_linear_load_combination_term_reorder_model_sha256",
    "workbench_nested_linear_load_combination_term_reorder_receipt_sha256",
    "workbench_nested_linear_load_combination_term_reorder_request_receipt_sha256",
    "workbench_nested_linear_load_combination_term_reorder_request_sha256",
    "workbench_nested_linear_load_combination_term_reorder_assembly_receipt_sha256",
    "workbench_nested_linear_load_combination_term_reorder_checkpoint_sha256",
    "workbench_nested_linear_load_combination_term_reorder_result_ir_sha256",
    "workbench_nested_linear_load_combination_term_reorder_recovery_sha256",
    "workbench_nested_linear_load_combination_term_reorder_report_ir_sha256",
    "workbench_nested_linear_load_combination_term_reorder_restart_passed",
}
V57_EXPECTED_KEYS = V56_EXPECTED_KEYS | V57_NESTED_LINEAR_LOAD_COMBINATION_TERM_REORDER_KEYS
V58_DIRECT_LINEAR_LOAD_COMBINATION_TERM_REORDER_KEYS = {
    "workbench_direct_linear_load_combination_term_reorder_surface_passed",
    "workbench_direct_linear_load_combination_term_reorder_model_sha256",
    "workbench_direct_linear_load_combination_term_reorder_receipt_sha256",
    "workbench_direct_linear_load_combination_term_reorder_request_receipt_sha256",
    "workbench_direct_linear_load_combination_term_reorder_request_sha256",
    "workbench_direct_linear_load_combination_term_reorder_assembly_receipt_sha256",
    "workbench_direct_linear_load_combination_term_reorder_checkpoint_sha256",
    "workbench_direct_linear_load_combination_term_reorder_result_ir_sha256",
    "workbench_direct_linear_load_combination_term_reorder_recovery_sha256",
    "workbench_direct_linear_load_combination_term_reorder_report_ir_sha256",
    "workbench_direct_linear_load_combination_term_reorder_restart_passed",
}
V58_EXPECTED_KEYS = V57_EXPECTED_KEYS | V58_DIRECT_LINEAR_LOAD_COMBINATION_TERM_REORDER_KEYS
V59_DIRECT_LINEAR_LOAD_COMBINATION_TERM_INSERT_KEYS = {
    "workbench_direct_linear_load_combination_term_insert_surface_passed",
    "workbench_direct_linear_load_combination_term_insert_model_sha256",
    "workbench_direct_linear_load_combination_term_insert_receipt_sha256",
    "workbench_direct_linear_load_combination_term_insert_request_receipt_sha256",
    "workbench_direct_linear_load_combination_term_insert_request_sha256",
    "workbench_direct_linear_load_combination_term_insert_assembly_receipt_sha256",
    "workbench_direct_linear_load_combination_term_insert_checkpoint_sha256",
    "workbench_direct_linear_load_combination_term_insert_result_ir_sha256",
    "workbench_direct_linear_load_combination_term_insert_recovery_sha256",
    "workbench_direct_linear_load_combination_term_insert_report_ir_sha256",
    "workbench_direct_linear_load_combination_term_insert_restart_passed",
}
V59_EXPECTED_KEYS = V58_EXPECTED_KEYS | V59_DIRECT_LINEAR_LOAD_COMBINATION_TERM_INSERT_KEYS
V60_NESTED_LINEAR_LOAD_COMBINATION_TERM_INSERT_KEYS = {
    "workbench_nested_linear_load_combination_term_insert_surface_passed",
    "workbench_nested_linear_load_combination_term_insert_model_sha256",
    "workbench_nested_linear_load_combination_term_insert_receipt_sha256",
    "workbench_nested_linear_load_combination_term_insert_request_receipt_sha256",
    "workbench_nested_linear_load_combination_term_insert_request_sha256",
    "workbench_nested_linear_load_combination_term_insert_assembly_receipt_sha256",
    "workbench_nested_linear_load_combination_term_insert_checkpoint_sha256",
    "workbench_nested_linear_load_combination_term_insert_result_ir_sha256",
    "workbench_nested_linear_load_combination_term_insert_recovery_sha256",
    "workbench_nested_linear_load_combination_term_insert_report_ir_sha256",
    "workbench_nested_linear_load_combination_term_insert_restart_passed",
}
V60_EXPECTED_KEYS = V59_EXPECTED_KEYS | V60_NESTED_LINEAR_LOAD_COMBINATION_TERM_INSERT_KEYS
V61_NODAL_LOAD_TARGET_EDIT_KEYS = {
    "workbench_nodal_load_target_edit_surface_passed",
    "workbench_nodal_load_target_edit_model_sha256",
    "workbench_nodal_load_target_edit_receipt_sha256",
    "workbench_nodal_load_target_edit_request_receipt_sha256",
    "workbench_nodal_load_target_edit_request_sha256",
    "workbench_nodal_load_target_edit_assembly_receipt_sha256",
    "workbench_nodal_load_target_edit_checkpoint_sha256",
    "workbench_nodal_load_target_edit_result_ir_sha256",
    "workbench_nodal_load_target_edit_recovery_sha256",
    "workbench_nodal_load_target_edit_report_ir_sha256",
    "workbench_nodal_load_target_edit_restart_passed",
}
V61_EXPECTED_KEYS = V60_EXPECTED_KEYS | V61_NODAL_LOAD_TARGET_EDIT_KEYS
V62_CONSTRAINT_TARGET_EDIT_KEYS = {
    "workbench_constraint_target_edit_surface_passed",
    "workbench_constraint_target_edit_model_sha256",
    "workbench_constraint_target_edit_receipt_sha256",
    "workbench_constraint_target_edit_request_receipt_sha256",
    "workbench_constraint_target_edit_request_sha256",
    "workbench_constraint_target_edit_assembly_receipt_sha256",
    "workbench_constraint_target_edit_checkpoint_sha256",
    "workbench_constraint_target_edit_result_ir_sha256",
    "workbench_constraint_target_edit_recovery_sha256",
    "workbench_constraint_target_edit_report_ir_sha256",
    "workbench_constraint_target_edit_restart_passed",
}
V62_EXPECTED_KEYS = V61_EXPECTED_KEYS | V62_CONSTRAINT_TARGET_EDIT_KEYS
V63_FIXED_CONSTRAINT_DOF_DELETE_KEYS = {
    "workbench_fixed_constraint_dof_delete_surface_passed",
    "workbench_fixed_constraint_dof_delete_model_sha256",
    "workbench_fixed_constraint_dof_delete_receipt_sha256",
    "workbench_fixed_constraint_dof_delete_request_receipt_sha256",
    "workbench_fixed_constraint_dof_delete_request_sha256",
    "workbench_fixed_constraint_dof_delete_assembly_receipt_sha256",
    "workbench_fixed_constraint_dof_delete_checkpoint_sha256",
    "workbench_fixed_constraint_dof_delete_result_ir_sha256",
    "workbench_fixed_constraint_dof_delete_recovery_sha256",
    "workbench_fixed_constraint_dof_delete_report_ir_sha256",
    "workbench_fixed_constraint_dof_delete_restart_passed",
}
V63_EXPECTED_KEYS = V62_EXPECTED_KEYS | V63_FIXED_CONSTRAINT_DOF_DELETE_KEYS
V64_FIXED_CONSTRAINT_DOF_ADD_KEYS = {
    "workbench_fixed_constraint_dof_add_surface_passed",
    "workbench_fixed_constraint_dof_add_model_sha256",
    "workbench_fixed_constraint_dof_add_receipt_sha256",
    "workbench_fixed_constraint_dof_add_request_receipt_sha256",
    "workbench_fixed_constraint_dof_add_request_sha256",
    "workbench_fixed_constraint_dof_add_assembly_receipt_sha256",
    "workbench_fixed_constraint_dof_add_checkpoint_sha256",
    "workbench_fixed_constraint_dof_add_result_ir_sha256",
    "workbench_fixed_constraint_dof_add_recovery_sha256",
    "workbench_fixed_constraint_dof_add_report_ir_sha256",
    "workbench_fixed_constraint_dof_add_restart_passed",
}
V64_EXPECTED_KEYS = V63_EXPECTED_KEYS | V64_FIXED_CONSTRAINT_DOF_ADD_KEYS
V65_FIXED_CONSTRAINT_DOF_REORDER_KEYS = {
    "workbench_fixed_constraint_dof_reorder_surface_passed",
    "workbench_fixed_constraint_dof_reorder_model_sha256",
    "workbench_fixed_constraint_dof_reorder_receipt_sha256",
    "workbench_fixed_constraint_dof_reorder_request_receipt_sha256",
    "workbench_fixed_constraint_dof_reorder_request_sha256",
    "workbench_fixed_constraint_dof_reorder_assembly_receipt_sha256",
    "workbench_fixed_constraint_dof_reorder_checkpoint_sha256",
    "workbench_fixed_constraint_dof_reorder_result_ir_sha256",
    "workbench_fixed_constraint_dof_reorder_recovery_sha256",
    "workbench_fixed_constraint_dof_reorder_report_ir_sha256",
    "workbench_fixed_constraint_dof_reorder_restart_passed",
}
V65_EXPECTED_KEYS = V64_EXPECTED_KEYS | V65_FIXED_CONSTRAINT_DOF_REORDER_KEYS
V66_FIXED_CONSTRAINT_IDENTITY_EDIT_KEYS = {
    "workbench_fixed_constraint_identity_edit_surface_passed",
    "workbench_fixed_constraint_identity_edit_model_sha256",
    "workbench_fixed_constraint_identity_edit_receipt_sha256",
    "workbench_fixed_constraint_identity_edit_request_receipt_sha256",
    "workbench_fixed_constraint_identity_edit_request_sha256",
    "workbench_fixed_constraint_identity_edit_assembly_receipt_sha256",
    "workbench_fixed_constraint_identity_edit_checkpoint_sha256",
    "workbench_fixed_constraint_identity_edit_result_ir_sha256",
    "workbench_fixed_constraint_identity_edit_recovery_sha256",
    "workbench_fixed_constraint_identity_edit_report_ir_sha256",
    "workbench_fixed_constraint_identity_edit_restart_passed",
}
V66_EXPECTED_KEYS = V65_EXPECTED_KEYS | V66_FIXED_CONSTRAINT_IDENTITY_EDIT_KEYS
V67_NODAL_LOAD_IDENTITY_EDIT_KEYS = {
    "workbench_nodal_load_identity_edit_surface_passed",
    "workbench_nodal_load_identity_edit_model_sha256",
    "workbench_nodal_load_identity_edit_receipt_sha256",
    "workbench_nodal_load_identity_edit_request_receipt_sha256",
    "workbench_nodal_load_identity_edit_request_sha256",
    "workbench_nodal_load_identity_edit_assembly_receipt_sha256",
    "workbench_nodal_load_identity_edit_checkpoint_sha256",
    "workbench_nodal_load_identity_edit_result_ir_sha256",
    "workbench_nodal_load_identity_edit_recovery_sha256",
    "workbench_nodal_load_identity_edit_report_ir_sha256",
    "workbench_nodal_load_identity_edit_restart_passed",
}
V67_EXPECTED_KEYS = V66_EXPECTED_KEYS | V67_NODAL_LOAD_IDENTITY_EDIT_KEYS
V68_LINEAR_LOAD_PATTERN_IDENTITY_EDIT_KEYS = {
    "workbench_linear_load_pattern_identity_edit_surface_passed",
    "workbench_linear_load_pattern_identity_edit_model_sha256",
    "workbench_linear_load_pattern_identity_edit_receipt_sha256",
    "workbench_linear_load_pattern_identity_edit_request_receipt_sha256",
    "workbench_linear_load_pattern_identity_edit_request_sha256",
    "workbench_linear_load_pattern_identity_edit_assembly_receipt_sha256",
    "workbench_linear_load_pattern_identity_edit_checkpoint_sha256",
    "workbench_linear_load_pattern_identity_edit_result_ir_sha256",
    "workbench_linear_load_pattern_identity_edit_recovery_sha256",
    "workbench_linear_load_pattern_identity_edit_report_ir_sha256",
    "workbench_linear_load_pattern_identity_edit_restart_passed",
}
V68_EXPECTED_KEYS = V67_EXPECTED_KEYS | V68_LINEAR_LOAD_PATTERN_IDENTITY_EDIT_KEYS
V69_LINEAR_MATERIAL_IDENTITY_EDIT_KEYS = {
    "workbench_linear_material_identity_edit_surface_passed",
    "workbench_linear_material_identity_edit_model_sha256",
    "workbench_linear_material_identity_edit_receipt_sha256",
    "workbench_linear_material_identity_edit_request_receipt_sha256",
    "workbench_linear_material_identity_edit_request_sha256",
    "workbench_linear_material_identity_edit_assembly_receipt_sha256",
    "workbench_linear_material_identity_edit_checkpoint_sha256",
    "workbench_linear_material_identity_edit_result_ir_sha256",
    "workbench_linear_material_identity_edit_recovery_sha256",
    "workbench_linear_material_identity_edit_report_ir_sha256",
    "workbench_linear_material_identity_edit_restart_passed",
}
V69_EXPECTED_KEYS = V68_EXPECTED_KEYS | V69_LINEAR_MATERIAL_IDENTITY_EDIT_KEYS
V70_FRAME_SECTION_IDENTITY_EDIT_KEYS = {
    "workbench_frame_section_identity_edit_surface_passed",
    "workbench_frame_section_identity_edit_model_sha256",
    "workbench_frame_section_identity_edit_receipt_sha256",
    "workbench_frame_section_identity_edit_request_receipt_sha256",
    "workbench_frame_section_identity_edit_request_sha256",
    "workbench_frame_section_identity_edit_assembly_receipt_sha256",
    "workbench_frame_section_identity_edit_checkpoint_sha256",
    "workbench_frame_section_identity_edit_result_ir_sha256",
    "workbench_frame_section_identity_edit_recovery_sha256",
    "workbench_frame_section_identity_edit_report_ir_sha256",
    "workbench_frame_section_identity_edit_restart_passed",
}
V70_EXPECTED_KEYS = V69_EXPECTED_KEYS | V70_FRAME_SECTION_IDENTITY_EDIT_KEYS
V71_TRUSS_SECTION_IDENTITY_EDIT_KEYS = {
    "workbench_truss_section_identity_edit_surface_passed",
    "workbench_truss_section_identity_edit_model_sha256",
    "workbench_truss_section_identity_edit_receipt_sha256",
    "workbench_truss_section_identity_edit_request_receipt_sha256",
    "workbench_truss_section_identity_edit_request_sha256",
    "workbench_truss_section_identity_edit_assembly_receipt_sha256",
    "workbench_truss_section_identity_edit_checkpoint_sha256",
    "workbench_truss_section_identity_edit_result_ir_sha256",
    "workbench_truss_section_identity_edit_recovery_sha256",
    "workbench_truss_section_identity_edit_report_ir_sha256",
    "workbench_truss_section_identity_edit_restart_passed",
}
V71_EXPECTED_KEYS = V70_EXPECTED_KEYS | V71_TRUSS_SECTION_IDENTITY_EDIT_KEYS
V72_NODE_IDENTITY_EDIT_KEYS = {
    "workbench_node_identity_edit_surface_passed",
    "workbench_node_identity_edit_model_sha256",
    "workbench_node_identity_edit_receipt_sha256",
    "workbench_node_identity_edit_request_receipt_sha256",
    "workbench_node_identity_edit_request_sha256",
    "workbench_node_identity_edit_assembly_receipt_sha256",
    "workbench_node_identity_edit_checkpoint_sha256",
    "workbench_node_identity_edit_result_ir_sha256",
    "workbench_node_identity_edit_recovery_sha256",
    "workbench_node_identity_edit_report_ir_sha256",
    "workbench_node_identity_edit_restart_passed",
}
V72_EXPECTED_KEYS = V71_EXPECTED_KEYS | V72_NODE_IDENTITY_EDIT_KEYS
V73_ELEMENT_IDENTITY_EDIT_KEYS = {
    "workbench_element_identity_edit_surface_passed",
    "workbench_element_identity_edit_model_sha256",
    "workbench_element_identity_edit_receipt_sha256",
    "workbench_element_identity_edit_request_receipt_sha256",
    "workbench_element_identity_edit_request_sha256",
    "workbench_element_identity_edit_assembly_receipt_sha256",
    "workbench_element_identity_edit_checkpoint_sha256",
    "workbench_element_identity_edit_result_ir_sha256",
    "workbench_element_identity_edit_recovery_sha256",
    "workbench_element_identity_edit_report_ir_sha256",
    "workbench_element_identity_edit_restart_passed",
}
V73_EXPECTED_KEYS = V72_EXPECTED_KEYS | V73_ELEMENT_IDENTITY_EDIT_KEYS
V74_LINEAR_LOAD_COMBINATION_IDENTITY_EDIT_KEYS = {
    "workbench_linear_load_combination_identity_edit_surface_passed",
    "workbench_linear_load_combination_identity_edit_model_sha256",
    "workbench_linear_load_combination_identity_edit_receipt_sha256",
    "workbench_linear_load_combination_identity_edit_request_receipt_sha256",
    "workbench_linear_load_combination_identity_edit_request_sha256",
    "workbench_linear_load_combination_identity_edit_assembly_receipt_sha256",
    "workbench_linear_load_combination_identity_edit_checkpoint_sha256",
    "workbench_linear_load_combination_identity_edit_result_ir_sha256",
    "workbench_linear_load_combination_identity_edit_recovery_sha256",
    "workbench_linear_load_combination_identity_edit_report_ir_sha256",
    "workbench_linear_load_combination_identity_edit_restart_passed",
}
V74_EXPECTED_KEYS = V73_EXPECTED_KEYS | V74_LINEAR_LOAD_COMBINATION_IDENTITY_EDIT_KEYS
V75_MODEL_IDENTITY_EDIT_KEYS = {
    "workbench_model_identity_edit_surface_passed",
    "workbench_model_identity_edit_model_sha256",
    "workbench_model_identity_edit_receipt_sha256",
    "workbench_model_identity_edit_request_receipt_sha256",
    "workbench_model_identity_edit_request_sha256",
    "workbench_model_identity_edit_assembly_receipt_sha256",
    "workbench_model_identity_edit_checkpoint_sha256",
    "workbench_model_identity_edit_result_ir_sha256",
    "workbench_model_identity_edit_recovery_sha256",
    "workbench_model_identity_edit_report_ir_sha256",
    "workbench_model_identity_edit_restart_passed",
}
V75_EXPECTED_KEYS = V74_EXPECTED_KEYS | V75_MODEL_IDENTITY_EDIT_KEYS
V76_NODE_IDENTITY_CASCADE_EDIT_KEYS = {
    "workbench_node_identity_cascade_edit_surface_passed",
    "workbench_node_identity_cascade_edit_model_sha256",
    "workbench_node_identity_cascade_edit_receipt_sha256",
    "workbench_node_identity_cascade_edit_request_receipt_sha256",
    "workbench_node_identity_cascade_edit_request_sha256",
    "workbench_node_identity_cascade_edit_assembly_receipt_sha256",
    "workbench_node_identity_cascade_edit_checkpoint_sha256",
    "workbench_node_identity_cascade_edit_result_ir_sha256",
    "workbench_node_identity_cascade_edit_recovery_sha256",
    "workbench_node_identity_cascade_edit_report_ir_sha256",
    "workbench_node_identity_cascade_edit_restart_passed",
}
V76_EXPECTED_KEYS = V75_EXPECTED_KEYS | V76_NODE_IDENTITY_CASCADE_EDIT_KEYS
V77_FRAME_SECTION_IDENTITY_CASCADE_EDIT_KEYS = {
    "workbench_frame_section_identity_cascade_edit_surface_passed",
    "workbench_frame_section_identity_cascade_edit_model_sha256",
    "workbench_frame_section_identity_cascade_edit_receipt_sha256",
    "workbench_frame_section_identity_cascade_edit_request_receipt_sha256",
    "workbench_frame_section_identity_cascade_edit_request_sha256",
    "workbench_frame_section_identity_cascade_edit_assembly_receipt_sha256",
    "workbench_frame_section_identity_cascade_edit_checkpoint_sha256",
    "workbench_frame_section_identity_cascade_edit_result_ir_sha256",
    "workbench_frame_section_identity_cascade_edit_recovery_sha256",
    "workbench_frame_section_identity_cascade_edit_report_ir_sha256",
    "workbench_frame_section_identity_cascade_edit_restart_passed",
}
V77_EXPECTED_KEYS = V76_EXPECTED_KEYS | V77_FRAME_SECTION_IDENTITY_CASCADE_EDIT_KEYS
V78_LINEAR_MATERIAL_IDENTITY_CASCADE_EDIT_KEYS = {
    "workbench_linear_material_identity_cascade_edit_surface_passed",
    "workbench_linear_material_identity_cascade_edit_model_sha256",
    "workbench_linear_material_identity_cascade_edit_receipt_sha256",
    "workbench_linear_material_identity_cascade_edit_request_receipt_sha256",
    "workbench_linear_material_identity_cascade_edit_request_sha256",
    "workbench_linear_material_identity_cascade_edit_assembly_receipt_sha256",
    "workbench_linear_material_identity_cascade_edit_checkpoint_sha256",
    "workbench_linear_material_identity_cascade_edit_result_ir_sha256",
    "workbench_linear_material_identity_cascade_edit_recovery_sha256",
    "workbench_linear_material_identity_cascade_edit_report_ir_sha256",
    "workbench_linear_material_identity_cascade_edit_restart_passed",
}
V78_EXPECTED_KEYS = V77_EXPECTED_KEYS | V78_LINEAR_MATERIAL_IDENTITY_CASCADE_EDIT_KEYS
V79_TRUSS_SECTION_IDENTITY_CASCADE_EDIT_KEYS = {
    "workbench_truss_section_identity_cascade_edit_surface_passed",
    "workbench_truss_section_identity_cascade_edit_model_sha256",
    "workbench_truss_section_identity_cascade_edit_receipt_sha256",
    "workbench_truss_section_identity_cascade_edit_request_receipt_sha256",
    "workbench_truss_section_identity_cascade_edit_request_sha256",
    "workbench_truss_section_identity_cascade_edit_assembly_receipt_sha256",
    "workbench_truss_section_identity_cascade_edit_checkpoint_sha256",
    "workbench_truss_section_identity_cascade_edit_result_ir_sha256",
    "workbench_truss_section_identity_cascade_edit_recovery_sha256",
    "workbench_truss_section_identity_cascade_edit_report_ir_sha256",
    "workbench_truss_section_identity_cascade_edit_restart_passed",
}
V79_EXPECTED_KEYS = V78_EXPECTED_KEYS | V79_TRUSS_SECTION_IDENTITY_CASCADE_EDIT_KEYS
INSTALLED_BACKEND_KEYS = {
    "schema_version",
    "backend_profile",
    "device_name",
    "cpu_backend",
    "execution_backend",
    "device_id",
    "cpu_backend_parity",
    "repeat_bitwise",
    "fp64",
    "deterministic",
    "fallback_count",
    "operator_device_resident",
    "h2d_bytes",
    "d2h_bytes",
    "synchronization_count",
    "kernel_launch_count",
    "device_buffer_bytes",
}


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("receipt must be a JSON object")
    return payload


def validate(
    payload: dict[str, Any],
    *,
    manifest: Path | None,
    installed_backend_receipt: Path | None,
    c2_receipt: Path | None,
    require_backend: str | None,
    require_authority: bool,
) -> list[str]:
    errors: list[str] = []
    schema_version = payload.get("schema_version")
    receipt_schema_version = schema_version
    is_v79_receipt = receipt_schema_version == "structural-native-distribution-e2e.v79"
    if is_v79_receipt:
        receipt_schema_version = "structural-native-distribution-e2e.v78"
    is_v78_receipt = receipt_schema_version == "structural-native-distribution-e2e.v78"
    if is_v78_receipt:
        receipt_schema_version = "structural-native-distribution-e2e.v77"
    is_v77_receipt = receipt_schema_version == "structural-native-distribution-e2e.v77"
    if is_v77_receipt:
        receipt_schema_version = "structural-native-distribution-e2e.v76"
    is_v76_receipt = receipt_schema_version == "structural-native-distribution-e2e.v76"
    if is_v76_receipt:
        receipt_schema_version = "structural-native-distribution-e2e.v75"
    is_v75_receipt = receipt_schema_version == "structural-native-distribution-e2e.v75"
    if is_v75_receipt:
        receipt_schema_version = "structural-native-distribution-e2e.v74"
    is_v74_receipt = receipt_schema_version == "structural-native-distribution-e2e.v74"
    if is_v74_receipt:
        receipt_schema_version = "structural-native-distribution-e2e.v73"
    is_v73_receipt = receipt_schema_version == "structural-native-distribution-e2e.v73"
    if is_v73_receipt:
        receipt_schema_version = "structural-native-distribution-e2e.v72"
    is_v57_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v57",
        "structural-native-distribution-e2e.v58",
        "structural-native-distribution-e2e.v59",
        "structural-native-distribution-e2e.v60",
        "structural-native-distribution-e2e.v61",
        "structural-native-distribution-e2e.v62",
        "structural-native-distribution-e2e.v63",
        "structural-native-distribution-e2e.v64",
        "structural-native-distribution-e2e.v65",
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v58_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v58",
        "structural-native-distribution-e2e.v59",
        "structural-native-distribution-e2e.v60",
        "structural-native-distribution-e2e.v61",
        "structural-native-distribution-e2e.v62",
        "structural-native-distribution-e2e.v63",
        "structural-native-distribution-e2e.v64",
        "structural-native-distribution-e2e.v65",
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v59_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v59",
        "structural-native-distribution-e2e.v60",
        "structural-native-distribution-e2e.v61",
        "structural-native-distribution-e2e.v62",
        "structural-native-distribution-e2e.v63",
        "structural-native-distribution-e2e.v64",
        "structural-native-distribution-e2e.v65",
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v60_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v60",
        "structural-native-distribution-e2e.v61",
        "structural-native-distribution-e2e.v62",
        "structural-native-distribution-e2e.v63",
        "structural-native-distribution-e2e.v64",
        "structural-native-distribution-e2e.v65",
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v61_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v61",
        "structural-native-distribution-e2e.v62",
        "structural-native-distribution-e2e.v63",
        "structural-native-distribution-e2e.v64",
        "structural-native-distribution-e2e.v65",
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v62_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v62",
        "structural-native-distribution-e2e.v63",
        "structural-native-distribution-e2e.v64",
        "structural-native-distribution-e2e.v65",
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v63_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v63",
        "structural-native-distribution-e2e.v64",
        "structural-native-distribution-e2e.v65",
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v64_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v64",
        "structural-native-distribution-e2e.v65",
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v65_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v65",
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v66_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v66",
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v67_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v67",
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v68_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v68",
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v69_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v69",
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v70_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v70",
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v71_receipt = receipt_schema_version in {
        "structural-native-distribution-e2e.v71",
        "structural-native-distribution-e2e.v72",
    }
    is_v72_receipt = receipt_schema_version == "structural-native-distribution-e2e.v72"
    latest_receipt_schema_version = (
        "structural-native-distribution-e2e.v56"
        if receipt_schema_version
        in {
            "structural-native-distribution-e2e.v57",
            "structural-native-distribution-e2e.v58",
            "structural-native-distribution-e2e.v59",
            "structural-native-distribution-e2e.v60",
            "structural-native-distribution-e2e.v61",
            "structural-native-distribution-e2e.v62",
            "structural-native-distribution-e2e.v63",
            "structural-native-distribution-e2e.v64",
            "structural-native-distribution-e2e.v65",
            "structural-native-distribution-e2e.v66",
            "structural-native-distribution-e2e.v67",
            "structural-native-distribution-e2e.v68",
            "structural-native-distribution-e2e.v69",
            "structural-native-distribution-e2e.v70",
            "structural-native-distribution-e2e.v71",
            "structural-native-distribution-e2e.v72",
        }
        else receipt_schema_version
    )
    expected_keys = {
        "structural-native-distribution-e2e.v1": V1_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v2": V2_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v3": V3_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v4": V4_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v5": V5_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v6": V6_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v7": V7_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v8": V8_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v9": V9_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v10": V10_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v11": V11_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v12": V12_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v13": V13_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v14": V14_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v15": V15_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v16": V16_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v17": V17_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v18": V18_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v19": V19_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v20": V20_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v21": V21_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v22": V22_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v23": V23_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v24": V24_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v25": V25_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v26": V26_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v27": V27_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v28": V28_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v29": V29_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v30": V30_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v31": V31_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v32": V32_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v33": V33_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v34": V34_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v35": V35_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v36": V36_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v37": V37_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v38": V38_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v39": V39_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v40": V40_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v41": V41_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v42": V42_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v43": V43_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v44": V44_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v45": V45_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v46": V46_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v47": V47_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v48": V48_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v49": V49_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v50": V50_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v51": V51_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v52": V52_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v53": V53_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v54": V54_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v55": V55_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v56": V56_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v57": V57_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v58": V58_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v59": V59_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v60": V60_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v61": V61_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v62": V62_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v63": V63_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v64": V64_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v65": V65_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v66": V66_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v67": V67_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v68": V68_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v69": V69_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v70": V70_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v71": V71_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v72": V72_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v73": V73_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v74": V74_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v75": V75_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v76": V76_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v77": V77_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v78": V78_EXPECTED_KEYS,
        "structural-native-distribution-e2e.v79": V79_EXPECTED_KEYS,
    }.get(schema_version)
    if expected_keys is None:
        errors.append("schema_version must be a supported structural native distribution receipt")
    elif set(payload) != expected_keys:
        errors.append(f"receipt keys differ from the exact {schema_version} contract")
    if receipt_schema_version == "structural-native-distribution-e2e.v72":
        receipt_schema_version = "structural-native-distribution-e2e.v71"
    if receipt_schema_version == "structural-native-distribution-e2e.v71":
        receipt_schema_version = "structural-native-distribution-e2e.v70"
    if receipt_schema_version == "structural-native-distribution-e2e.v70":
        receipt_schema_version = "structural-native-distribution-e2e.v69"
    if receipt_schema_version == "structural-native-distribution-e2e.v69":
        receipt_schema_version = "structural-native-distribution-e2e.v68"
    if receipt_schema_version == "structural-native-distribution-e2e.v68":
        receipt_schema_version = "structural-native-distribution-e2e.v67"
    if receipt_schema_version == "structural-native-distribution-e2e.v67":
        receipt_schema_version = "structural-native-distribution-e2e.v66"
    if receipt_schema_version == "structural-native-distribution-e2e.v66":
        receipt_schema_version = "structural-native-distribution-e2e.v65"
    if receipt_schema_version == "structural-native-distribution-e2e.v65":
        receipt_schema_version = "structural-native-distribution-e2e.v64"
    if receipt_schema_version == "structural-native-distribution-e2e.v64":
        receipt_schema_version = "structural-native-distribution-e2e.v63"
    if receipt_schema_version == "structural-native-distribution-e2e.v63":
        receipt_schema_version = "structural-native-distribution-e2e.v62"
    if receipt_schema_version == "structural-native-distribution-e2e.v62":
        receipt_schema_version = "structural-native-distribution-e2e.v61"
    if receipt_schema_version == "structural-native-distribution-e2e.v61":
        receipt_schema_version = "structural-native-distribution-e2e.v60"
    if receipt_schema_version == "structural-native-distribution-e2e.v60":
        receipt_schema_version = "structural-native-distribution-e2e.v59"
    if receipt_schema_version == "structural-native-distribution-e2e.v59":
        receipt_schema_version = "structural-native-distribution-e2e.v58"
    if receipt_schema_version == "structural-native-distribution-e2e.v58":
        receipt_schema_version = "structural-native-distribution-e2e.v57"
    if receipt_schema_version == "structural-native-distribution-e2e.v57":
        receipt_schema_version = "structural-native-distribution-e2e.v56"
    if receipt_schema_version == "structural-native-distribution-e2e.v56":
        receipt_schema_version = "structural-native-distribution-e2e.v55"
    if receipt_schema_version == "structural-native-distribution-e2e.v55":
        receipt_schema_version = "structural-native-distribution-e2e.v54"
    if receipt_schema_version == "structural-native-distribution-e2e.v54":
        receipt_schema_version = "structural-native-distribution-e2e.v53"
    if receipt_schema_version == "structural-native-distribution-e2e.v53":
        receipt_schema_version = "structural-native-distribution-e2e.v52"
    if receipt_schema_version == "structural-native-distribution-e2e.v52":
        receipt_schema_version = "structural-native-distribution-e2e.v51"
    if receipt_schema_version == "structural-native-distribution-e2e.v51":
        receipt_schema_version = "structural-native-distribution-e2e.v50"
    if receipt_schema_version == "structural-native-distribution-e2e.v50":
        receipt_schema_version = "structural-native-distribution-e2e.v49"
    if receipt_schema_version == "structural-native-distribution-e2e.v49":
        receipt_schema_version = "structural-native-distribution-e2e.v48"
    if receipt_schema_version == "structural-native-distribution-e2e.v48":
        receipt_schema_version = "structural-native-distribution-e2e.v47"
    if receipt_schema_version == "structural-native-distribution-e2e.v47":
        receipt_schema_version = "structural-native-distribution-e2e.v46"
    if receipt_schema_version == "structural-native-distribution-e2e.v46":
        receipt_schema_version = "structural-native-distribution-e2e.v45"
    if receipt_schema_version == "structural-native-distribution-e2e.v45":
        receipt_schema_version = "structural-native-distribution-e2e.v44"
    cumulative_receipt_schema_version = receipt_schema_version
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v32",
        "structural-native-distribution-e2e.v33",
        "structural-native-distribution-e2e.v34",
        "structural-native-distribution-e2e.v35",
        "structural-native-distribution-e2e.v36",
        "structural-native-distribution-e2e.v37",
        "structural-native-distribution-e2e.v38",
        "structural-native-distribution-e2e.v39",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        cumulative_receipt_schema_version = "structural-native-distribution-e2e.v31"
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v14",
        "structural-native-distribution-e2e.v15",
        "structural-native-distribution-e2e.v16",
        "structural-native-distribution-e2e.v17",
        "structural-native-distribution-e2e.v18",
        "structural-native-distribution-e2e.v19",
        "structural-native-distribution-e2e.v20",
        "structural-native-distribution-e2e.v21",
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        schema_version = "structural-native-distribution-e2e.v13"
    backend = payload.get("backend_profile")
    if backend not in {"cpu_only", "rocm"}:
        errors.append("backend_profile must be cpu_only or rocm")
    if require_backend is not None and backend != require_backend:
        errors.append(f"backend_profile must be {require_backend}")
    linkage = payload.get("linkage")
    if linkage not in {"shared", "static"}:
        errors.append("linkage must be shared or static")
    if backend == "rocm" and linkage != "shared":
        errors.append("ROCm distribution receipt must use shared linkage")
    for name in (
        "source_sha256",
        "bundle_manifest_sha256",
        "result_ir_sha256",
        "report_pdf_sha256",
        "installed_backend_receipt_sha256",
    ):
        if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
            errors.append(f"{name} must be a lowercase SHA-256 identity")
    if schema_version in {
        "structural-native-distribution-e2e.v2",
        "structural-native-distribution-e2e.v3",
        "structural-native-distribution-e2e.v4",
        "structural-native-distribution-e2e.v5",
        "structural-native-distribution-e2e.v6",
        "structural-native-distribution-e2e.v7",
        "structural-native-distribution-e2e.v8",
        "structural-native-distribution-e2e.v9",
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        for name in (
            "mgt_source_sha256",
            "mgt_import_health_sha256",
            "mgt_result_ir_sha256",
            "mgt_report_pdf_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v79_receipt:
        for name in (
            "workbench_truss_section_identity_cascade_edit_surface_passed",
            "workbench_truss_section_identity_cascade_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_truss_section_identity_cascade_edit_model_sha256",
            "workbench_truss_section_identity_cascade_edit_receipt_sha256",
            "workbench_truss_section_identity_cascade_edit_request_receipt_sha256",
            "workbench_truss_section_identity_cascade_edit_request_sha256",
            "workbench_truss_section_identity_cascade_edit_assembly_receipt_sha256",
            "workbench_truss_section_identity_cascade_edit_checkpoint_sha256",
            "workbench_truss_section_identity_cascade_edit_result_ir_sha256",
            "workbench_truss_section_identity_cascade_edit_recovery_sha256",
            "workbench_truss_section_identity_cascade_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v78_receipt:
        for name in (
            "workbench_linear_material_identity_cascade_edit_surface_passed",
            "workbench_linear_material_identity_cascade_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_linear_material_identity_cascade_edit_model_sha256",
            "workbench_linear_material_identity_cascade_edit_receipt_sha256",
            "workbench_linear_material_identity_cascade_edit_request_receipt_sha256",
            "workbench_linear_material_identity_cascade_edit_request_sha256",
            "workbench_linear_material_identity_cascade_edit_assembly_receipt_sha256",
            "workbench_linear_material_identity_cascade_edit_checkpoint_sha256",
            "workbench_linear_material_identity_cascade_edit_result_ir_sha256",
            "workbench_linear_material_identity_cascade_edit_recovery_sha256",
            "workbench_linear_material_identity_cascade_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v77_receipt:
        for name in (
            "workbench_frame_section_identity_cascade_edit_surface_passed",
            "workbench_frame_section_identity_cascade_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_frame_section_identity_cascade_edit_model_sha256",
            "workbench_frame_section_identity_cascade_edit_receipt_sha256",
            "workbench_frame_section_identity_cascade_edit_request_receipt_sha256",
            "workbench_frame_section_identity_cascade_edit_request_sha256",
            "workbench_frame_section_identity_cascade_edit_assembly_receipt_sha256",
            "workbench_frame_section_identity_cascade_edit_checkpoint_sha256",
            "workbench_frame_section_identity_cascade_edit_result_ir_sha256",
            "workbench_frame_section_identity_cascade_edit_recovery_sha256",
            "workbench_frame_section_identity_cascade_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v76_receipt:
        for name in (
            "workbench_node_identity_cascade_edit_surface_passed",
            "workbench_node_identity_cascade_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_node_identity_cascade_edit_model_sha256",
            "workbench_node_identity_cascade_edit_receipt_sha256",
            "workbench_node_identity_cascade_edit_request_receipt_sha256",
            "workbench_node_identity_cascade_edit_request_sha256",
            "workbench_node_identity_cascade_edit_assembly_receipt_sha256",
            "workbench_node_identity_cascade_edit_checkpoint_sha256",
            "workbench_node_identity_cascade_edit_result_ir_sha256",
            "workbench_node_identity_cascade_edit_recovery_sha256",
            "workbench_node_identity_cascade_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v75_receipt:
        for name in (
            "workbench_model_identity_edit_surface_passed",
            "workbench_model_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_model_identity_edit_model_sha256",
            "workbench_model_identity_edit_receipt_sha256",
            "workbench_model_identity_edit_request_receipt_sha256",
            "workbench_model_identity_edit_request_sha256",
            "workbench_model_identity_edit_assembly_receipt_sha256",
            "workbench_model_identity_edit_checkpoint_sha256",
            "workbench_model_identity_edit_result_ir_sha256",
            "workbench_model_identity_edit_recovery_sha256",
            "workbench_model_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v74_receipt:
        for name in (
            "workbench_linear_load_combination_identity_edit_surface_passed",
            "workbench_linear_load_combination_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_linear_load_combination_identity_edit_model_sha256",
            "workbench_linear_load_combination_identity_edit_receipt_sha256",
            "workbench_linear_load_combination_identity_edit_request_receipt_sha256",
            "workbench_linear_load_combination_identity_edit_request_sha256",
            "workbench_linear_load_combination_identity_edit_assembly_receipt_sha256",
            "workbench_linear_load_combination_identity_edit_checkpoint_sha256",
            "workbench_linear_load_combination_identity_edit_result_ir_sha256",
            "workbench_linear_load_combination_identity_edit_recovery_sha256",
            "workbench_linear_load_combination_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    for name in (
        "single_product_abi",
        "install_passed",
        "update_passed",
        "rollback_passed",
        "package_consumer_passed",
        "workbench_restart_passed",
        "workbench_direct_parity_passed",
    ):
        if payload.get(name) is not True:
            errors.append(f"{name} must be true")
    if schema_version in {
        "structural-native-distribution-e2e.v2",
        "structural-native-distribution-e2e.v3",
        "structural-native-distribution-e2e.v4",
        "structural-native-distribution-e2e.v5",
        "structural-native-distribution-e2e.v6",
        "structural-native-distribution-e2e.v7",
        "structural-native-distribution-e2e.v8",
        "structural-native-distribution-e2e.v9",
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        for name in (
            "mgt_workbench_restart_passed",
            "mgt_workbench_direct_parity_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
    if schema_version in {
        "structural-native-distribution-e2e.v3",
        "structural-native-distribution-e2e.v4",
        "structural-native-distribution-e2e.v5",
        "structural-native-distribution-e2e.v6",
        "structural-native-distribution-e2e.v7",
        "structural-native-distribution-e2e.v8",
        "structural-native-distribution-e2e.v9",
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        for name in (
            "workbench_operator_surface_passed",
            "mgt_workbench_operator_surface_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in ("workbench_review_decision", "mgt_workbench_review_decision"):
            if payload.get(name) != "review":
                errors.append(f"{name} must preserve the non-promoting review decision")
        for name in (
            "workbench_review_sha256",
            "workbench_export_sha256",
            "mgt_workbench_review_sha256",
            "mgt_workbench_export_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if schema_version in {
        "structural-native-distribution-e2e.v4",
        "structural-native-distribution-e2e.v5",
        "structural-native-distribution-e2e.v6",
        "structural-native-distribution-e2e.v7",
        "structural-native-distribution-e2e.v8",
        "structural-native-distribution-e2e.v9",
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        for name in (
            "workbench_catalog_surface_passed",
            "workbench_evidence_surface_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in ("workbench_catalog_sha256", "workbench_evidence_sha256"):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if schema_version in {
        "structural-native-distribution-e2e.v5",
        "structural-native-distribution-e2e.v6",
        "structural-native-distribution-e2e.v7",
        "structural-native-distribution-e2e.v8",
        "structural-native-distribution-e2e.v9",
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        for name in (
            "evidence_builder_check_passed",
            "evidence_builder_build_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "evidence_builder_check_sha256",
            "evidence_builder_build_sha256",
            "evidence_builder_manifest_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if schema_version in {
        "structural-native-distribution-e2e.v6",
        "structural-native-distribution-e2e.v7",
        "structural-native-distribution-e2e.v8",
        "structural-native-distribution-e2e.v9",
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        for name in (
            "catalog_builder_check_passed",
            "catalog_builder_build_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "catalog_builder_check_sha256",
            "catalog_builder_build_sha256",
            "catalog_builder_output_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if schema_version in {
        "structural-native-distribution-e2e.v7",
        "structural-native-distribution-e2e.v8",
        "structural-native-distribution-e2e.v9",
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        if payload.get("workbench_localized_pdf_surface_passed") is not True:
            errors.append("workbench_localized_pdf_surface_passed must be true")
        for name in (
            "workbench_localized_pdf_en_us_sha256",
            "workbench_localized_pdf_ko_kr_sha256",
            "workbench_localized_pdf_en_us_receipt_sha256",
            "workbench_localized_pdf_ko_kr_receipt_sha256",
            "localized_report_font_sha256",
            "localized_report_font_license_sha256",
            "localized_report_font_provenance_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
        if payload.get("workbench_localized_pdf_en_us_sha256") == payload.get(
            "workbench_localized_pdf_ko_kr_sha256"
        ):
            errors.append("localized en-US and ko-KR PDF identities must differ")
    if schema_version in {
        "structural-native-distribution-e2e.v8",
        "structural-native-distribution-e2e.v9",
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        if payload.get("workbench_model_view_surface_passed") is not True:
            errors.append("workbench_model_view_surface_passed must be true")
        model_view_identities = []
        for name in (
            "workbench_model_view_isometric_sha256",
            "workbench_model_view_xy_sha256",
            "workbench_model_view_xz_sha256",
            "workbench_model_view_yz_sha256",
        ):
            identity = payload.get(name)
            if not isinstance(identity, str) or not SHA256.fullmatch(identity):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
            else:
                model_view_identities.append(identity)
        if len(model_view_identities) == 4 and len(set(model_view_identities)) != 4:
            errors.append("all four model topology projection identities must differ")
    if schema_version in {
        "structural-native-distribution-e2e.v9",
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        if payload.get("workbench_model_edit_surface_passed") is not True:
            errors.append("workbench_model_edit_surface_passed must be true")
        for name in (
            "workbench_model_edit_model_sha256",
            "workbench_model_edit_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if schema_version in {
        "structural-native-distribution-e2e.v10",
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        if payload.get("workbench_result_view_surface_passed") is not True:
            errors.append("workbench_result_view_surface_passed must be true")
        result_view_identities = []
        for name in (
            "workbench_result_view_top_displacement_sha256",
            "workbench_result_view_drift_ratio_sha256",
            "workbench_result_view_base_shear_sha256",
            "workbench_result_view_residual_inf_sha256",
            "workbench_result_view_window_sha256",
        ):
            identity = payload.get(name)
            if not isinstance(identity, str) or not SHA256.fullmatch(identity):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
            else:
                result_view_identities.append(identity)
        if len(result_view_identities) == 5 and len(set(result_view_identities)) != 5:
            errors.append("all response channel and explicit-window identities must differ")
    if schema_version in {
        "structural-native-distribution-e2e.v11",
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        if payload.get("workbench_deformed_view_surface_passed") is not True:
            errors.append("workbench_deformed_view_surface_passed must be true")
        deformed_view_identities = []
        for name in (
            "workbench_deformed_view_isometric_sha256",
            "workbench_deformed_view_xy_sha256",
            "workbench_deformed_view_xz_sha256",
            "workbench_deformed_view_yz_sha256",
            "workbench_deformed_view_explicit_sha256",
        ):
            identity = payload.get(name)
            if not isinstance(identity, str) or not SHA256.fullmatch(identity):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
            else:
                deformed_view_identities.append(identity)
        if len(deformed_view_identities) == 5 and len(set(deformed_view_identities)) != 5:
            errors.append("all deformed-shape projection and explicit identities must differ")
    if schema_version in {
        "structural-native-distribution-e2e.v12",
        "structural-native-distribution-e2e.v13",
    }:
        if payload.get("workbench_localized_result_views_surface_passed") is not True:
            errors.append("workbench_localized_result_views_surface_passed must be true")
        for name in (
            "workbench_result_view_ko_kr_sha256",
            "workbench_deformed_view_ko_kr_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
        if payload.get("workbench_result_view_ko_kr_sha256") == payload.get(
            "workbench_result_view_top_displacement_sha256"
        ):
            errors.append("localized en-US and ko-KR response-view identities must differ")
        if payload.get("workbench_deformed_view_ko_kr_sha256") == payload.get(
            "workbench_deformed_view_isometric_sha256"
        ):
            errors.append("localized en-US and ko-KR deformed-view identities must differ")
    if schema_version == "structural-native-distribution-e2e.v13":
        if payload.get("workbench_localized_model_view_surface_passed") is not True:
            errors.append("workbench_localized_model_view_surface_passed must be true")
        localized_model_view_identity = payload.get("workbench_model_view_ko_kr_sha256")
        if not isinstance(localized_model_view_identity, str) or not SHA256.fullmatch(
            localized_model_view_identity
        ):
            errors.append("workbench_model_view_ko_kr_sha256 must be a lowercase SHA-256 identity")
        if localized_model_view_identity == payload.get(
            "workbench_model_view_isometric_sha256"
        ):
            errors.append("localized en-US and ko-KR model-view identities must differ")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v14",
        "structural-native-distribution-e2e.v15",
        "structural-native-distribution-e2e.v16",
        "structural-native-distribution-e2e.v17",
        "structural-native-distribution-e2e.v18",
        "structural-native-distribution-e2e.v19",
        "structural-native-distribution-e2e.v20",
        "structural-native-distribution-e2e.v21",
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        for name in (
            "model_ir_linear_workbench_restart_passed",
            "model_ir_linear_workbench_direct_parity_passed",
            "model_ir_linear_workbench_operator_surface_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        if payload.get("model_ir_linear_workbench_review_decision") != "review":
            errors.append(
                "model_ir_linear_workbench_review_decision must preserve the non-promoting review decision"
            )
        for name in (
            "model_ir_linear_workbench_review_sha256",
            "model_ir_linear_workbench_export_sha256",
            "model_ir_linear_result_ir_sha256",
            "model_ir_linear_result_recovery_ir_sha256",
            "model_ir_linear_report_pdf_sha256",
            "model_ir_linear_pdf_receipt_sha256",
            "model_ir_linear_report_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v15",
        "structural-native-distribution-e2e.v16",
        "structural-native-distribution-e2e.v17",
        "structural-native-distribution-e2e.v18",
        "structural-native-distribution-e2e.v19",
        "structural-native-distribution-e2e.v20",
        "structural-native-distribution-e2e.v21",
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("model_ir_linear_localized_pdf_surface_passed") is not True:
            errors.append("model_ir_linear_localized_pdf_surface_passed must be true")
        for name in (
            "model_ir_linear_localized_pdf_en_us_sha256",
            "model_ir_linear_localized_pdf_ko_kr_sha256",
            "model_ir_linear_localized_pdf_en_us_receipt_sha256",
            "model_ir_linear_localized_pdf_ko_kr_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
        if payload.get("model_ir_linear_localized_pdf_en_us_sha256") == payload.get(
            "model_ir_linear_localized_pdf_ko_kr_sha256"
        ):
            errors.append("ModelIR-linear localized en-US and ko-KR PDF identities must differ")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v16",
        "structural-native-distribution-e2e.v17",
        "structural-native-distribution-e2e.v18",
        "structural-native-distribution-e2e.v19",
        "structural-native-distribution-e2e.v20",
        "structural-native-distribution-e2e.v21",
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        for name in (
            "mgt_model_ir_linear_workbench_restart_passed",
            "mgt_model_ir_linear_workbench_direct_parity_passed",
            "mgt_model_ir_linear_workbench_operator_surface_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        if payload.get("mgt_model_ir_linear_workbench_review_decision") != "review":
            errors.append(
                "mgt_model_ir_linear_workbench_review_decision must preserve the non-promoting review decision"
            )
        for name in (
            "mgt_model_ir_linear_workbench_review_sha256",
            "mgt_model_ir_linear_workbench_export_sha256",
            "mgt_model_ir_linear_source_sha256",
            "mgt_model_ir_linear_import_health_sha256",
            "mgt_model_ir_linear_result_ir_sha256",
            "mgt_model_ir_linear_result_recovery_ir_sha256",
            "mgt_model_ir_linear_report_pdf_sha256",
            "mgt_model_ir_linear_pdf_receipt_sha256",
            "mgt_model_ir_linear_report_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v17",
        "structural-native-distribution-e2e.v18",
        "structural-native-distribution-e2e.v19",
        "structural-native-distribution-e2e.v20",
        "structural-native-distribution-e2e.v21",
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_nodal_load_edit_surface_passed") is not True:
            errors.append("workbench_nodal_load_edit_surface_passed must be true")
        for name in (
            "workbench_nodal_load_edit_model_sha256",
            "workbench_nodal_load_edit_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v18",
        "structural-native-distribution-e2e.v19",
        "structural-native-distribution-e2e.v20",
        "structural-native-distribution-e2e.v21",
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_constraint_value_edit_surface_passed") is not True:
            errors.append("workbench_constraint_value_edit_surface_passed must be true")
        for name in (
            "workbench_constraint_value_edit_model_sha256",
            "workbench_constraint_value_edit_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v19",
        "structural-native-distribution-e2e.v20",
        "structural-native-distribution-e2e.v21",
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        for name in (
            "workbench_linear_material_edit_surface_passed",
            "workbench_frame_section_edit_surface_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_linear_material_edit_model_sha256",
            "workbench_linear_material_edit_receipt_sha256",
            "workbench_frame_section_edit_model_sha256",
            "workbench_frame_section_edit_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v20",
        "structural-native-distribution-e2e.v21",
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_frame_element_orientation_edit_surface_passed") is not True:
            errors.append("workbench_frame_element_orientation_edit_surface_passed must be true")
        for name in (
            "workbench_frame_element_orientation_edit_model_sha256",
            "workbench_frame_element_orientation_edit_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v21",
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_element_connectivity_edit_surface_passed") is not True:
            errors.append("workbench_element_connectivity_edit_surface_passed must be true")
        for name in (
            "workbench_element_connectivity_edit_model_sha256",
            "workbench_element_connectivity_edit_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v22",
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_model_linear_request_create_surface_passed") is not True:
            errors.append("workbench_model_linear_request_create_surface_passed must be true")
        for name in (
            "workbench_model_linear_request_create_request_sha256",
            "workbench_model_linear_request_create_receipt_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v23",
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_frame3d_member_add_surface_passed") is not True:
            errors.append("workbench_frame3d_member_add_surface_passed must be true")
        for name in (
            "workbench_frame3d_member_add_model_sha256",
            "workbench_frame3d_member_add_receipt_sha256",
            "workbench_frame3d_member_add_request_sha256",
            "workbench_frame3d_member_add_result_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v24",
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_nodal_load_add_surface_passed") is not True:
            errors.append("workbench_nodal_load_add_surface_passed must be true")
        for name in (
            "workbench_nodal_load_add_model_sha256",
            "workbench_nodal_load_add_receipt_sha256",
            "workbench_nodal_load_add_request_sha256",
            "workbench_nodal_load_add_result_ir_sha256",
            "workbench_nodal_load_add_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v25",
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_fixed_constraint_add_surface_passed") is not True:
            errors.append("workbench_fixed_constraint_add_surface_passed must be true")
        for name in (
            "workbench_fixed_constraint_add_model_sha256",
            "workbench_fixed_constraint_add_receipt_sha256",
            "workbench_fixed_constraint_add_request_sha256",
            "workbench_fixed_constraint_add_result_ir_sha256",
            "workbench_fixed_constraint_add_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v26",
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_linear_load_pattern_add_surface_passed") is not True:
            errors.append("workbench_linear_load_pattern_add_surface_passed must be true")
        for name in (
            "workbench_linear_load_pattern_add_model_sha256",
            "workbench_linear_load_pattern_add_receipt_sha256",
            "workbench_linear_load_pattern_add_request_sha256",
            "workbench_linear_load_pattern_add_result_ir_sha256",
            "workbench_linear_load_pattern_add_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v27",
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_linear_material_add_surface_passed") is not True:
            errors.append("workbench_linear_material_add_surface_passed must be true")
        for name in (
            "workbench_linear_material_add_model_sha256",
            "workbench_linear_material_add_receipt_sha256",
            "workbench_linear_material_add_composed_model_sha256",
            "workbench_linear_material_add_request_sha256",
            "workbench_linear_material_add_result_ir_sha256",
            "workbench_linear_material_add_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v28",
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_frame_section_add_surface_passed") is not True:
            errors.append("workbench_frame_section_add_surface_passed must be true")
        for name in (
            "workbench_frame_section_add_model_sha256",
            "workbench_frame_section_add_receipt_sha256",
            "workbench_frame_section_add_composed_model_sha256",
            "workbench_frame_section_add_request_sha256",
            "workbench_frame_section_add_result_ir_sha256",
            "workbench_frame_section_add_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v29",
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_frame_element_properties_edit_surface_passed") is not True:
            errors.append("workbench_frame_element_properties_edit_surface_passed must be true")
        for name in (
            "workbench_frame_element_properties_edit_model_sha256",
            "workbench_frame_element_properties_edit_receipt_sha256",
            "workbench_frame_element_properties_edit_request_sha256",
            "workbench_frame_element_properties_edit_result_ir_sha256",
            "workbench_frame_element_properties_edit_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version in {
        "structural-native-distribution-e2e.v30",
        "structural-native-distribution-e2e.v31",
    }:
        if payload.get("workbench_truss3d_authoring_surface_passed") is not True:
            errors.append("workbench_truss3d_authoring_surface_passed must be true")
        for name in (
            "workbench_truss3d_authoring_section_model_sha256",
            "workbench_truss3d_authoring_section_receipt_sha256",
            "workbench_truss3d_authoring_member_model_sha256",
            "workbench_truss3d_authoring_member_receipt_sha256",
            "workbench_truss3d_authoring_composed_model_sha256",
            "workbench_truss3d_authoring_request_sha256",
            "workbench_truss3d_authoring_result_ir_sha256",
            "workbench_truss3d_authoring_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if cumulative_receipt_schema_version == "structural-native-distribution-e2e.v31":
        if payload.get("workbench_truss3d_editing_surface_passed") is not True:
            errors.append("workbench_truss3d_editing_surface_passed must be true")
        for name in (
            "workbench_truss3d_editing_section_model_sha256",
            "workbench_truss3d_editing_section_receipt_sha256",
            "workbench_truss3d_editing_properties_model_sha256",
            "workbench_truss3d_editing_properties_receipt_sha256",
            "workbench_truss3d_editing_section_result_ir_sha256",
            "workbench_truss3d_editing_request_sha256",
            "workbench_truss3d_editing_result_ir_sha256",
            "workbench_truss3d_editing_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v32",
        "structural-native-distribution-e2e.v33",
        "structural-native-distribution-e2e.v34",
        "structural-native-distribution-e2e.v35",
        "structural-native-distribution-e2e.v36",
        "structural-native-distribution-e2e.v37",
        "structural-native-distribution-e2e.v38",
        "structural-native-distribution-e2e.v39",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_truss3d_leaf_deletion_surface_passed") is not True:
            errors.append("workbench_truss3d_leaf_deletion_surface_passed must be true")
        for name in (
            "workbench_truss3d_leaf_deletion_model_sha256",
            "workbench_truss3d_leaf_deletion_receipt_sha256",
            "workbench_truss3d_leaf_deletion_request_sha256",
            "workbench_truss3d_leaf_deletion_result_ir_sha256",
            "workbench_truss3d_leaf_deletion_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v33",
        "structural-native-distribution-e2e.v34",
        "structural-native-distribution-e2e.v35",
        "structural-native-distribution-e2e.v36",
        "structural-native-distribution-e2e.v37",
        "structural-native-distribution-e2e.v38",
        "structural-native-distribution-e2e.v39",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_frame3d_leaf_deletion_surface_passed") is not True:
            errors.append("workbench_frame3d_leaf_deletion_surface_passed must be true")
        for name in (
            "workbench_frame3d_leaf_deletion_model_sha256",
            "workbench_frame3d_leaf_deletion_receipt_sha256",
            "workbench_frame3d_leaf_deletion_request_sha256",
            "workbench_frame3d_leaf_deletion_result_ir_sha256",
            "workbench_frame3d_leaf_deletion_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v34",
        "structural-native-distribution-e2e.v35",
        "structural-native-distribution-e2e.v36",
        "structural-native-distribution-e2e.v37",
        "structural-native-distribution-e2e.v38",
        "structural-native-distribution-e2e.v39",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_fixed_constraint_delete_surface_passed") is not True:
            errors.append("workbench_fixed_constraint_delete_surface_passed must be true")
        for name in (
            "workbench_fixed_constraint_delete_model_sha256",
            "workbench_fixed_constraint_delete_receipt_sha256",
            "workbench_fixed_constraint_delete_request_sha256",
            "workbench_fixed_constraint_delete_result_ir_sha256",
            "workbench_fixed_constraint_delete_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v35",
        "structural-native-distribution-e2e.v36",
        "structural-native-distribution-e2e.v37",
        "structural-native-distribution-e2e.v38",
        "structural-native-distribution-e2e.v39",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_nodal_load_delete_surface_passed") is not True:
            errors.append("workbench_nodal_load_delete_surface_passed must be true")
        for name in (
            "workbench_nodal_load_delete_model_sha256",
            "workbench_nodal_load_delete_receipt_sha256",
            "workbench_nodal_load_delete_request_sha256",
            "workbench_nodal_load_delete_result_ir_sha256",
            "workbench_nodal_load_delete_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v36",
        "structural-native-distribution-e2e.v37",
        "structural-native-distribution-e2e.v38",
        "structural-native-distribution-e2e.v39",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_linear_load_pattern_delete_surface_passed") is not True:
            errors.append("workbench_linear_load_pattern_delete_surface_passed must be true")
        for name in (
            "workbench_linear_load_pattern_delete_model_sha256",
            "workbench_linear_load_pattern_delete_receipt_sha256",
            "workbench_linear_load_pattern_delete_request_sha256",
            "workbench_linear_load_pattern_delete_result_ir_sha256",
            "workbench_linear_load_pattern_delete_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v37",
        "structural-native-distribution-e2e.v38",
        "structural-native-distribution-e2e.v39",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_linear_material_delete_surface_passed") is not True:
            errors.append("workbench_linear_material_delete_surface_passed must be true")
        for name in (
            "workbench_linear_material_delete_model_sha256",
            "workbench_linear_material_delete_receipt_sha256",
            "workbench_linear_material_delete_request_sha256",
            "workbench_linear_material_delete_result_ir_sha256",
            "workbench_linear_material_delete_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v38",
        "structural-native-distribution-e2e.v39",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_frame_section_delete_surface_passed") is not True:
            errors.append("workbench_frame_section_delete_surface_passed must be true")
        for name in (
            "workbench_frame_section_delete_model_sha256",
            "workbench_frame_section_delete_receipt_sha256",
            "workbench_frame_section_delete_request_sha256",
            "workbench_frame_section_delete_result_ir_sha256",
            "workbench_frame_section_delete_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v39",
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_truss_section_delete_surface_passed") is not True:
            errors.append("workbench_truss_section_delete_surface_passed must be true")
        for name in (
            "workbench_truss_section_delete_model_sha256",
            "workbench_truss_section_delete_receipt_sha256",
            "workbench_truss_section_delete_request_sha256",
            "workbench_truss_section_delete_result_ir_sha256",
            "workbench_truss_section_delete_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v40",
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_node_add_surface_passed") is not True:
            errors.append("workbench_node_add_surface_passed must be true")
        for name in (
            "workbench_node_add_model_sha256",
            "workbench_node_add_receipt_sha256",
            "workbench_node_add_composed_model_sha256",
            "workbench_node_add_request_sha256",
            "workbench_node_add_result_ir_sha256",
            "workbench_node_add_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v41",
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_orphan_node_delete_surface_passed") is not True:
            errors.append("workbench_orphan_node_delete_surface_passed must be true")
        for name in (
            "workbench_orphan_node_delete_model_sha256",
            "workbench_orphan_node_delete_receipt_sha256",
            "workbench_orphan_node_delete_request_sha256",
            "workbench_orphan_node_delete_result_ir_sha256",
            "workbench_orphan_node_delete_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v42",
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_linear_load_combination_add_surface_passed") is not True:
            errors.append(
                "workbench_linear_load_combination_add_surface_passed must be true"
            )
        for name in (
            "workbench_linear_load_combination_add_model_sha256",
            "workbench_linear_load_combination_add_receipt_sha256",
            "workbench_linear_load_combination_add_validation_sha256",
            "workbench_linear_load_combination_add_view_sha256",
            "workbench_linear_load_combination_add_solver_rejection_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version in {
        "structural-native-distribution-e2e.v43",
        "structural-native-distribution-e2e.v44",
    }:
        if payload.get("workbench_linear_load_combination_delete_surface_passed") is not True:
            errors.append(
                "workbench_linear_load_combination_delete_surface_passed must be true"
            )
        for name in (
            "workbench_linear_load_combination_delete_model_sha256",
            "workbench_linear_load_combination_delete_receipt_sha256",
            "workbench_linear_load_combination_delete_request_sha256",
            "workbench_linear_load_combination_delete_result_ir_sha256",
            "workbench_linear_load_combination_delete_recovery_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if receipt_schema_version == "structural-native-distribution-e2e.v44":
        for name in (
            "workbench_linear_load_combination_execution_surface_passed",
            "workbench_linear_load_combination_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_linear_load_combination_request_receipt_sha256",
            "workbench_linear_load_combination_request_sha256",
            "workbench_linear_load_combination_assembly_receipt_sha256",
            "workbench_linear_load_combination_checkpoint_sha256",
            "workbench_linear_load_combination_result_ir_sha256",
            "workbench_linear_load_combination_recovery_sha256",
            "workbench_linear_load_combination_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v45",
        "structural-native-distribution-e2e.v46",
        "structural-native-distribution-e2e.v47",
        "structural-native-distribution-e2e.v48",
        "structural-native-distribution-e2e.v49",
        "structural-native-distribution-e2e.v50",
        "structural-native-distribution-e2e.v51",
        "structural-native-distribution-e2e.v52",
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_direct_linear_load_combination_surface_passed",
            "workbench_direct_linear_load_combination_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_direct_linear_load_combination_model_sha256",
            "workbench_direct_linear_load_combination_edit_receipt_sha256",
            "workbench_direct_linear_load_combination_request_receipt_sha256",
            "workbench_direct_linear_load_combination_request_sha256",
            "workbench_direct_linear_load_combination_assembly_receipt_sha256",
            "workbench_direct_linear_load_combination_checkpoint_sha256",
            "workbench_direct_linear_load_combination_result_ir_sha256",
            "workbench_direct_linear_load_combination_recovery_sha256",
            "workbench_direct_linear_load_combination_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v46",
        "structural-native-distribution-e2e.v47",
        "structural-native-distribution-e2e.v48",
        "structural-native-distribution-e2e.v49",
        "structural-native-distribution-e2e.v50",
        "structural-native-distribution-e2e.v51",
        "structural-native-distribution-e2e.v52",
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_nested_linear_load_combination_surface_passed",
            "workbench_nested_linear_load_combination_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nested_linear_load_combination_model_sha256",
            "workbench_nested_linear_load_combination_edit_receipt_sha256",
            "workbench_nested_linear_load_combination_request_receipt_sha256",
            "workbench_nested_linear_load_combination_request_sha256",
            "workbench_nested_linear_load_combination_assembly_receipt_sha256",
            "workbench_nested_linear_load_combination_checkpoint_sha256",
            "workbench_nested_linear_load_combination_result_ir_sha256",
            "workbench_nested_linear_load_combination_recovery_sha256",
            "workbench_nested_linear_load_combination_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v47",
        "structural-native-distribution-e2e.v48",
        "structural-native-distribution-e2e.v49",
        "structural-native-distribution-e2e.v50",
        "structural-native-distribution-e2e.v51",
        "structural-native-distribution-e2e.v52",
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_direct_linear_load_combination_delete_surface_passed",
            "workbench_direct_linear_load_combination_delete_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_direct_linear_load_combination_delete_model_sha256",
            "workbench_direct_linear_load_combination_delete_receipt_sha256",
            "workbench_direct_linear_load_combination_delete_request_sha256",
            "workbench_direct_linear_load_combination_delete_assembly_receipt_sha256",
            "workbench_direct_linear_load_combination_delete_checkpoint_sha256",
            "workbench_direct_linear_load_combination_delete_result_ir_sha256",
            "workbench_direct_linear_load_combination_delete_recovery_sha256",
            "workbench_direct_linear_load_combination_delete_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v48",
        "structural-native-distribution-e2e.v49",
        "structural-native-distribution-e2e.v50",
        "structural-native-distribution-e2e.v51",
        "structural-native-distribution-e2e.v52",
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_nested_linear_load_combination_delete_surface_passed",
            "workbench_nested_linear_load_combination_delete_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nested_linear_load_combination_delete_model_sha256",
            "workbench_nested_linear_load_combination_delete_receipt_sha256",
            "workbench_nested_linear_load_combination_delete_request_receipt_sha256",
            "workbench_nested_linear_load_combination_delete_request_sha256",
            "workbench_nested_linear_load_combination_delete_assembly_receipt_sha256",
            "workbench_nested_linear_load_combination_delete_checkpoint_sha256",
            "workbench_nested_linear_load_combination_delete_result_ir_sha256",
            "workbench_nested_linear_load_combination_delete_recovery_sha256",
            "workbench_nested_linear_load_combination_delete_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v49",
        "structural-native-distribution-e2e.v50",
        "structural-native-distribution-e2e.v51",
        "structural-native-distribution-e2e.v52",
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_direct_linear_load_combination_factor_edit_surface_passed",
            "workbench_direct_linear_load_combination_factor_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_direct_linear_load_combination_factor_edit_model_sha256",
            "workbench_direct_linear_load_combination_factor_edit_receipt_sha256",
            "workbench_direct_linear_load_combination_factor_edit_request_receipt_sha256",
            "workbench_direct_linear_load_combination_factor_edit_request_sha256",
            "workbench_direct_linear_load_combination_factor_edit_assembly_receipt_sha256",
            "workbench_direct_linear_load_combination_factor_edit_checkpoint_sha256",
            "workbench_direct_linear_load_combination_factor_edit_result_ir_sha256",
            "workbench_direct_linear_load_combination_factor_edit_recovery_sha256",
            "workbench_direct_linear_load_combination_factor_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v50",
        "structural-native-distribution-e2e.v51",
        "structural-native-distribution-e2e.v52",
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_nested_linear_load_combination_factor_edit_surface_passed",
            "workbench_nested_linear_load_combination_factor_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nested_linear_load_combination_factor_edit_model_sha256",
            "workbench_nested_linear_load_combination_factor_edit_receipt_sha256",
            "workbench_nested_linear_load_combination_factor_edit_request_receipt_sha256",
            "workbench_nested_linear_load_combination_factor_edit_request_sha256",
            "workbench_nested_linear_load_combination_factor_edit_assembly_receipt_sha256",
            "workbench_nested_linear_load_combination_factor_edit_checkpoint_sha256",
            "workbench_nested_linear_load_combination_factor_edit_result_ir_sha256",
            "workbench_nested_linear_load_combination_factor_edit_recovery_sha256",
            "workbench_nested_linear_load_combination_factor_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v51",
        "structural-native-distribution-e2e.v52",
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_direct_linear_load_combination_reference_edit_surface_passed",
            "workbench_direct_linear_load_combination_reference_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_direct_linear_load_combination_reference_edit_model_sha256",
            "workbench_direct_linear_load_combination_reference_edit_receipt_sha256",
            "workbench_direct_linear_load_combination_reference_edit_request_receipt_sha256",
            "workbench_direct_linear_load_combination_reference_edit_request_sha256",
            "workbench_direct_linear_load_combination_reference_edit_assembly_receipt_sha256",
            "workbench_direct_linear_load_combination_reference_edit_checkpoint_sha256",
            "workbench_direct_linear_load_combination_reference_edit_result_ir_sha256",
            "workbench_direct_linear_load_combination_reference_edit_recovery_sha256",
            "workbench_direct_linear_load_combination_reference_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v52",
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_nested_linear_load_combination_reference_edit_surface_passed",
            "workbench_nested_linear_load_combination_reference_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nested_linear_load_combination_reference_edit_model_sha256",
            "workbench_nested_linear_load_combination_reference_edit_receipt_sha256",
            "workbench_nested_linear_load_combination_reference_edit_request_receipt_sha256",
            "workbench_nested_linear_load_combination_reference_edit_request_sha256",
            "workbench_nested_linear_load_combination_reference_edit_assembly_receipt_sha256",
            "workbench_nested_linear_load_combination_reference_edit_checkpoint_sha256",
            "workbench_nested_linear_load_combination_reference_edit_result_ir_sha256",
            "workbench_nested_linear_load_combination_reference_edit_recovery_sha256",
            "workbench_nested_linear_load_combination_reference_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v53",
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_direct_linear_load_combination_term_add_surface_passed",
            "workbench_direct_linear_load_combination_term_add_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_direct_linear_load_combination_term_add_model_sha256",
            "workbench_direct_linear_load_combination_term_add_receipt_sha256",
            "workbench_direct_linear_load_combination_term_add_request_receipt_sha256",
            "workbench_direct_linear_load_combination_term_add_request_sha256",
            "workbench_direct_linear_load_combination_term_add_assembly_receipt_sha256",
            "workbench_direct_linear_load_combination_term_add_checkpoint_sha256",
            "workbench_direct_linear_load_combination_term_add_result_ir_sha256",
            "workbench_direct_linear_load_combination_term_add_recovery_sha256",
            "workbench_direct_linear_load_combination_term_add_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v54",
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_direct_linear_load_combination_term_delete_surface_passed",
            "workbench_direct_linear_load_combination_term_delete_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_direct_linear_load_combination_term_delete_model_sha256",
            "workbench_direct_linear_load_combination_term_delete_receipt_sha256",
            "workbench_direct_linear_load_combination_term_delete_request_receipt_sha256",
            "workbench_direct_linear_load_combination_term_delete_request_sha256",
            "workbench_direct_linear_load_combination_term_delete_assembly_receipt_sha256",
            "workbench_direct_linear_load_combination_term_delete_checkpoint_sha256",
            "workbench_direct_linear_load_combination_term_delete_result_ir_sha256",
            "workbench_direct_linear_load_combination_term_delete_recovery_sha256",
            "workbench_direct_linear_load_combination_term_delete_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version in {
        "structural-native-distribution-e2e.v55",
        "structural-native-distribution-e2e.v56",
    }:
        for name in (
            "workbench_nested_linear_load_combination_term_add_surface_passed",
            "workbench_nested_linear_load_combination_term_add_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nested_linear_load_combination_term_add_model_sha256",
            "workbench_nested_linear_load_combination_term_add_receipt_sha256",
            "workbench_nested_linear_load_combination_term_add_request_receipt_sha256",
            "workbench_nested_linear_load_combination_term_add_request_sha256",
            "workbench_nested_linear_load_combination_term_add_assembly_receipt_sha256",
            "workbench_nested_linear_load_combination_term_add_checkpoint_sha256",
            "workbench_nested_linear_load_combination_term_add_result_ir_sha256",
            "workbench_nested_linear_load_combination_term_add_recovery_sha256",
            "workbench_nested_linear_load_combination_term_add_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if latest_receipt_schema_version == "structural-native-distribution-e2e.v56":
        for name in (
            "workbench_nested_linear_load_combination_term_delete_surface_passed",
            "workbench_nested_linear_load_combination_term_delete_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nested_linear_load_combination_term_delete_model_sha256",
            "workbench_nested_linear_load_combination_term_delete_receipt_sha256",
            "workbench_nested_linear_load_combination_term_delete_request_receipt_sha256",
            "workbench_nested_linear_load_combination_term_delete_request_sha256",
            "workbench_nested_linear_load_combination_term_delete_assembly_receipt_sha256",
            "workbench_nested_linear_load_combination_term_delete_checkpoint_sha256",
            "workbench_nested_linear_load_combination_term_delete_result_ir_sha256",
            "workbench_nested_linear_load_combination_term_delete_recovery_sha256",
            "workbench_nested_linear_load_combination_term_delete_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v57_receipt:
        for name in (
            "workbench_nested_linear_load_combination_term_reorder_surface_passed",
            "workbench_nested_linear_load_combination_term_reorder_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nested_linear_load_combination_term_reorder_model_sha256",
            "workbench_nested_linear_load_combination_term_reorder_receipt_sha256",
            "workbench_nested_linear_load_combination_term_reorder_request_receipt_sha256",
            "workbench_nested_linear_load_combination_term_reorder_request_sha256",
            "workbench_nested_linear_load_combination_term_reorder_assembly_receipt_sha256",
            "workbench_nested_linear_load_combination_term_reorder_checkpoint_sha256",
            "workbench_nested_linear_load_combination_term_reorder_result_ir_sha256",
            "workbench_nested_linear_load_combination_term_reorder_recovery_sha256",
            "workbench_nested_linear_load_combination_term_reorder_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v58_receipt:
        for name in (
            "workbench_direct_linear_load_combination_term_reorder_surface_passed",
            "workbench_direct_linear_load_combination_term_reorder_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_direct_linear_load_combination_term_reorder_model_sha256",
            "workbench_direct_linear_load_combination_term_reorder_receipt_sha256",
            "workbench_direct_linear_load_combination_term_reorder_request_receipt_sha256",
            "workbench_direct_linear_load_combination_term_reorder_request_sha256",
            "workbench_direct_linear_load_combination_term_reorder_assembly_receipt_sha256",
            "workbench_direct_linear_load_combination_term_reorder_checkpoint_sha256",
            "workbench_direct_linear_load_combination_term_reorder_result_ir_sha256",
            "workbench_direct_linear_load_combination_term_reorder_recovery_sha256",
            "workbench_direct_linear_load_combination_term_reorder_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v59_receipt:
        for name in (
            "workbench_direct_linear_load_combination_term_insert_surface_passed",
            "workbench_direct_linear_load_combination_term_insert_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_direct_linear_load_combination_term_insert_model_sha256",
            "workbench_direct_linear_load_combination_term_insert_receipt_sha256",
            "workbench_direct_linear_load_combination_term_insert_request_receipt_sha256",
            "workbench_direct_linear_load_combination_term_insert_request_sha256",
            "workbench_direct_linear_load_combination_term_insert_assembly_receipt_sha256",
            "workbench_direct_linear_load_combination_term_insert_checkpoint_sha256",
            "workbench_direct_linear_load_combination_term_insert_result_ir_sha256",
            "workbench_direct_linear_load_combination_term_insert_recovery_sha256",
            "workbench_direct_linear_load_combination_term_insert_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v60_receipt:
        for name in (
            "workbench_nested_linear_load_combination_term_insert_surface_passed",
            "workbench_nested_linear_load_combination_term_insert_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nested_linear_load_combination_term_insert_model_sha256",
            "workbench_nested_linear_load_combination_term_insert_receipt_sha256",
            "workbench_nested_linear_load_combination_term_insert_request_receipt_sha256",
            "workbench_nested_linear_load_combination_term_insert_request_sha256",
            "workbench_nested_linear_load_combination_term_insert_assembly_receipt_sha256",
            "workbench_nested_linear_load_combination_term_insert_checkpoint_sha256",
            "workbench_nested_linear_load_combination_term_insert_result_ir_sha256",
            "workbench_nested_linear_load_combination_term_insert_recovery_sha256",
            "workbench_nested_linear_load_combination_term_insert_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v61_receipt:
        for name in (
            "workbench_nodal_load_target_edit_surface_passed",
            "workbench_nodal_load_target_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nodal_load_target_edit_model_sha256",
            "workbench_nodal_load_target_edit_receipt_sha256",
            "workbench_nodal_load_target_edit_request_receipt_sha256",
            "workbench_nodal_load_target_edit_request_sha256",
            "workbench_nodal_load_target_edit_assembly_receipt_sha256",
            "workbench_nodal_load_target_edit_checkpoint_sha256",
            "workbench_nodal_load_target_edit_result_ir_sha256",
            "workbench_nodal_load_target_edit_recovery_sha256",
            "workbench_nodal_load_target_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v62_receipt:
        for name in (
            "workbench_constraint_target_edit_surface_passed",
            "workbench_constraint_target_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_constraint_target_edit_model_sha256",
            "workbench_constraint_target_edit_receipt_sha256",
            "workbench_constraint_target_edit_request_receipt_sha256",
            "workbench_constraint_target_edit_request_sha256",
            "workbench_constraint_target_edit_assembly_receipt_sha256",
            "workbench_constraint_target_edit_checkpoint_sha256",
            "workbench_constraint_target_edit_result_ir_sha256",
            "workbench_constraint_target_edit_recovery_sha256",
            "workbench_constraint_target_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v63_receipt:
        for name in (
            "workbench_fixed_constraint_dof_delete_surface_passed",
            "workbench_fixed_constraint_dof_delete_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_fixed_constraint_dof_delete_model_sha256",
            "workbench_fixed_constraint_dof_delete_receipt_sha256",
            "workbench_fixed_constraint_dof_delete_request_receipt_sha256",
            "workbench_fixed_constraint_dof_delete_request_sha256",
            "workbench_fixed_constraint_dof_delete_assembly_receipt_sha256",
            "workbench_fixed_constraint_dof_delete_checkpoint_sha256",
            "workbench_fixed_constraint_dof_delete_result_ir_sha256",
            "workbench_fixed_constraint_dof_delete_recovery_sha256",
            "workbench_fixed_constraint_dof_delete_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v64_receipt:
        for name in (
            "workbench_fixed_constraint_dof_add_surface_passed",
            "workbench_fixed_constraint_dof_add_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_fixed_constraint_dof_add_model_sha256",
            "workbench_fixed_constraint_dof_add_receipt_sha256",
            "workbench_fixed_constraint_dof_add_request_receipt_sha256",
            "workbench_fixed_constraint_dof_add_request_sha256",
            "workbench_fixed_constraint_dof_add_assembly_receipt_sha256",
            "workbench_fixed_constraint_dof_add_checkpoint_sha256",
            "workbench_fixed_constraint_dof_add_result_ir_sha256",
            "workbench_fixed_constraint_dof_add_recovery_sha256",
            "workbench_fixed_constraint_dof_add_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v65_receipt:
        for name in (
            "workbench_fixed_constraint_dof_reorder_surface_passed",
            "workbench_fixed_constraint_dof_reorder_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_fixed_constraint_dof_reorder_model_sha256",
            "workbench_fixed_constraint_dof_reorder_receipt_sha256",
            "workbench_fixed_constraint_dof_reorder_request_receipt_sha256",
            "workbench_fixed_constraint_dof_reorder_request_sha256",
            "workbench_fixed_constraint_dof_reorder_assembly_receipt_sha256",
            "workbench_fixed_constraint_dof_reorder_checkpoint_sha256",
            "workbench_fixed_constraint_dof_reorder_result_ir_sha256",
            "workbench_fixed_constraint_dof_reorder_recovery_sha256",
            "workbench_fixed_constraint_dof_reorder_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v66_receipt:
        for name in (
            "workbench_fixed_constraint_identity_edit_surface_passed",
            "workbench_fixed_constraint_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_fixed_constraint_identity_edit_model_sha256",
            "workbench_fixed_constraint_identity_edit_receipt_sha256",
            "workbench_fixed_constraint_identity_edit_request_receipt_sha256",
            "workbench_fixed_constraint_identity_edit_request_sha256",
            "workbench_fixed_constraint_identity_edit_assembly_receipt_sha256",
            "workbench_fixed_constraint_identity_edit_checkpoint_sha256",
            "workbench_fixed_constraint_identity_edit_result_ir_sha256",
            "workbench_fixed_constraint_identity_edit_recovery_sha256",
            "workbench_fixed_constraint_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v67_receipt:
        for name in (
            "workbench_nodal_load_identity_edit_surface_passed",
            "workbench_nodal_load_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_nodal_load_identity_edit_model_sha256",
            "workbench_nodal_load_identity_edit_receipt_sha256",
            "workbench_nodal_load_identity_edit_request_receipt_sha256",
            "workbench_nodal_load_identity_edit_request_sha256",
            "workbench_nodal_load_identity_edit_assembly_receipt_sha256",
            "workbench_nodal_load_identity_edit_checkpoint_sha256",
            "workbench_nodal_load_identity_edit_result_ir_sha256",
            "workbench_nodal_load_identity_edit_recovery_sha256",
            "workbench_nodal_load_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v68_receipt:
        for name in (
            "workbench_linear_load_pattern_identity_edit_surface_passed",
            "workbench_linear_load_pattern_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_linear_load_pattern_identity_edit_model_sha256",
            "workbench_linear_load_pattern_identity_edit_receipt_sha256",
            "workbench_linear_load_pattern_identity_edit_request_receipt_sha256",
            "workbench_linear_load_pattern_identity_edit_request_sha256",
            "workbench_linear_load_pattern_identity_edit_assembly_receipt_sha256",
            "workbench_linear_load_pattern_identity_edit_checkpoint_sha256",
            "workbench_linear_load_pattern_identity_edit_result_ir_sha256",
            "workbench_linear_load_pattern_identity_edit_recovery_sha256",
            "workbench_linear_load_pattern_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v69_receipt:
        for name in (
            "workbench_linear_material_identity_edit_surface_passed",
            "workbench_linear_material_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_linear_material_identity_edit_model_sha256",
            "workbench_linear_material_identity_edit_receipt_sha256",
            "workbench_linear_material_identity_edit_request_receipt_sha256",
            "workbench_linear_material_identity_edit_request_sha256",
            "workbench_linear_material_identity_edit_assembly_receipt_sha256",
            "workbench_linear_material_identity_edit_checkpoint_sha256",
            "workbench_linear_material_identity_edit_result_ir_sha256",
            "workbench_linear_material_identity_edit_recovery_sha256",
            "workbench_linear_material_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v70_receipt:
        for name in (
            "workbench_frame_section_identity_edit_surface_passed",
            "workbench_frame_section_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_frame_section_identity_edit_model_sha256",
            "workbench_frame_section_identity_edit_receipt_sha256",
            "workbench_frame_section_identity_edit_request_receipt_sha256",
            "workbench_frame_section_identity_edit_request_sha256",
            "workbench_frame_section_identity_edit_assembly_receipt_sha256",
            "workbench_frame_section_identity_edit_checkpoint_sha256",
            "workbench_frame_section_identity_edit_result_ir_sha256",
            "workbench_frame_section_identity_edit_recovery_sha256",
            "workbench_frame_section_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v71_receipt:
        for name in (
            "workbench_truss_section_identity_edit_surface_passed",
            "workbench_truss_section_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_truss_section_identity_edit_model_sha256",
            "workbench_truss_section_identity_edit_receipt_sha256",
            "workbench_truss_section_identity_edit_request_receipt_sha256",
            "workbench_truss_section_identity_edit_request_sha256",
            "workbench_truss_section_identity_edit_assembly_receipt_sha256",
            "workbench_truss_section_identity_edit_checkpoint_sha256",
            "workbench_truss_section_identity_edit_result_ir_sha256",
            "workbench_truss_section_identity_edit_recovery_sha256",
            "workbench_truss_section_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v72_receipt:
        for name in (
            "workbench_node_identity_edit_surface_passed",
            "workbench_node_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_node_identity_edit_model_sha256",
            "workbench_node_identity_edit_receipt_sha256",
            "workbench_node_identity_edit_request_receipt_sha256",
            "workbench_node_identity_edit_request_sha256",
            "workbench_node_identity_edit_assembly_receipt_sha256",
            "workbench_node_identity_edit_checkpoint_sha256",
            "workbench_node_identity_edit_result_ir_sha256",
            "workbench_node_identity_edit_recovery_sha256",
            "workbench_node_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    if is_v73_receipt:
        for name in (
            "workbench_element_identity_edit_surface_passed",
            "workbench_element_identity_edit_restart_passed",
        ):
            if payload.get(name) is not True:
                errors.append(f"{name} must be true")
        for name in (
            "workbench_element_identity_edit_model_sha256",
            "workbench_element_identity_edit_receipt_sha256",
            "workbench_element_identity_edit_request_receipt_sha256",
            "workbench_element_identity_edit_request_sha256",
            "workbench_element_identity_edit_assembly_receipt_sha256",
            "workbench_element_identity_edit_checkpoint_sha256",
            "workbench_element_identity_edit_result_ir_sha256",
            "workbench_element_identity_edit_recovery_sha256",
            "workbench_element_identity_edit_report_ir_sha256",
        ):
            if not isinstance(payload.get(name), str) or not SHA256.fullmatch(payload[name]):
                errors.append(f"{name} must be a lowercase SHA-256 identity")
    for name in ("python_lookup_count", "node_lookup_count", "fallback_count"):
        if type(payload.get(name)) is not int or payload[name] != 0:
            errors.append(f"{name} must be integer zero")
    expected_authority = "hosted_cpu_c5" if backend == "cpu_only" else "approved_rocm_c5"
    if payload.get("authority") != expected_authority:
        errors.append(f"authority must be {expected_authority} for {backend}")
    if not isinstance(payload.get("release_id"), str) or not re.fullmatch(
        r"[A-Za-z0-9._-]{1,128}", payload["release_id"]
    ):
        errors.append("release_id is not a portable bounded token")
    if backend == "cpu_only":
        if payload.get("approved_device_runner") is not False:
            errors.append("CPU receipt approved_device_runner must be false")
        if payload.get("c2_receipt_sha256") is not None:
            errors.append("CPU receipt must not claim a C2 device receipt")
    else:
        if payload.get("approved_device_runner") is not True:
            errors.append("ROCm receipt approved_device_runner must be true")
        if not isinstance(payload.get("c2_receipt_sha256"), str) or not SHA256.fullmatch(
            payload["c2_receipt_sha256"]
        ):
            errors.append("ROCm c2_receipt_sha256 must be a SHA-256 identity")
    if installed_backend_receipt is not None:
        digest = "sha256:" + hashlib.sha256(installed_backend_receipt.read_bytes()).hexdigest()
        if payload.get("installed_backend_receipt_sha256") != digest:
            errors.append("installed backend receipt hash does not match")
        installed = read_json(installed_backend_receipt)
        if set(installed) != INSTALLED_BACKEND_KEYS:
            errors.append("installed backend receipt keys differ from the exact v1 contract")
        if installed.get("schema_version") != "structural-native-installed-backend.v1":
            errors.append("installed backend receipt schema is invalid")
        if installed.get("backend_profile") != backend:
            errors.append("installed backend receipt profile does not match")
        for name in ("cpu_backend_parity", "repeat_bitwise", "fp64", "deterministic"):
            if installed.get(name) is not True:
                errors.append(f"installed backend {name} must be true")
        if installed.get("fallback_count") != 0:
            errors.append("installed backend fallback_count must be zero")
        if installed.get("cpu_backend") != 1:
            errors.append("installed backend CPU reference identity must be 1")
        if backend == "cpu_only":
            expected_installed = {
                "execution_backend": 1,
                "device_id": -1,
                "operator_device_resident": False,
                "h2d_bytes": 0,
                "d2h_bytes": 0,
                "synchronization_count": 0,
                "kernel_launch_count": 0,
                "device_buffer_bytes": 0,
            }
            for name, expected in expected_installed.items():
                if installed.get(name) != expected:
                    errors.append(f"installed CPU backend {name} is invalid")
        else:
            expected_installed = {
                "execution_backend": 2,
                "device_id": 0,
                "operator_device_resident": True,
            }
            for name, expected in expected_installed.items():
                if installed.get(name) != expected:
                    errors.append(f"installed ROCm backend {name} is invalid")
            for name in (
                "h2d_bytes",
                "d2h_bytes",
                "synchronization_count",
                "kernel_launch_count",
                "device_buffer_bytes",
            ):
                value = installed.get(name)
                if type(value) is not int or value <= 0:
                    errors.append(f"installed ROCm backend {name} must be positive")
    if c2_receipt is not None:
        digest = "sha256:" + hashlib.sha256(c2_receipt.read_bytes()).hexdigest()
        if payload.get("c2_receipt_sha256") != digest:
            errors.append("C2 receipt hash does not match")
        c2 = read_json(c2_receipt)
        expected_c2 = {
            "schema_version": "native-full-residual-backend-hip-receipt.v1",
            "backend": "amd_rocm_hip",
            "fallback_count": 0,
            "fp64": True,
            "deterministic": True,
            "operator_device_resident": True,
            "cpu_hip_parity": True,
            "hip_repeat_bitwise": True,
            "single_entry_symbol": "sa_get_api_v1",
            "parity_pass": True,
        }
        for name, expected in expected_c2.items():
            if c2.get(name) != expected:
                errors.append(f"C2 receipt {name} is invalid")
    if manifest is not None:
        digest = "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest()
        if payload.get("bundle_manifest_sha256") != digest:
            errors.append("bundle_manifest_sha256 does not match the supplied manifest")
        manifest_payload = read_json(manifest)
        expected_profile = "cpu_only" if backend == "cpu_only" else "rocm"
        if manifest_payload.get("backend_profile") != expected_profile:
            errors.append("receipt backend does not match distribution manifest")
        if manifest_payload.get("release_id") != payload.get("release_id"):
            errors.append("receipt release does not match distribution manifest")
        if manifest_payload.get("source_sha256") != payload.get("source_sha256"):
            errors.append("receipt source identity does not match distribution manifest")
        expected_execution_authority = (
            "cpu_build_candidate" if backend == "cpu_only" else "rocm_build_candidate"
        )
        if manifest_payload.get("execution_authority") != expected_execution_authority:
            errors.append("distribution manifest has an invalid build-time authority")
    if require_authority:
        if manifest is None:
            errors.append("authoritative validation requires the distribution manifest")
        if installed_backend_receipt is None:
            errors.append("authoritative validation requires the installed backend receipt")
        if backend == "rocm" and c2_receipt is None:
            errors.append("authoritative ROCm validation requires the C2 execution receipt")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--installed-backend-receipt", type=Path)
    parser.add_argument("--c2-receipt", type=Path)
    parser.add_argument("--require-backend", choices=("cpu_only", "rocm"))
    parser.add_argument("--require-authority", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    try:
        payload = read_json(arguments.receipt)
        errors = validate(
            payload,
            manifest=arguments.manifest,
            installed_backend_receipt=arguments.installed_backend_receipt,
            c2_receipt=arguments.c2_receipt,
            require_backend=arguments.require_backend,
            require_authority=arguments.require_authority,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors = [str(error)]
        payload = {}
    result = {
        "schema_version": "structural-native-distribution-receipt-validation.v1",
        "valid": not errors,
        "authoritative": bool(arguments.require_authority and not errors),
        "backend_profile": payload.get("backend_profile"),
        "authority": payload.get("authority"),
        "errors": errors,
    }
    if arguments.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    elif errors:
        for error in errors:
            print(error, file=sys.stderr)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
