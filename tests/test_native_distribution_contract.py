import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build_native_distribution.sh"
RUN = ROOT / "scripts" / "run_native_distribution_e2e.sh"
RUN_ROCM = ROOT / "scripts" / "run_native_rocm_distribution_e2e.sh"
CHECK = ROOT / "scripts" / "check_native_distribution_receipt.py"
LIB = ROOT / "native" / "crates" / "structural-distribution" / "src" / "lib.rs"
FFI_BUILD = ROOT / "native" / "crates" / "structural-ffi" / "build.rs"
ROOTFS_RUN = ROOT / "scripts" / "run_native_rootfs_isolation_e2e.sh"


def run_checker(tmp_path: Path, receipt: dict, manifest: dict) -> subprocess.CompletedProcess[str]:
    receipt_path = tmp_path / "receipt.json"
    manifest_path = tmp_path / "structural-distribution.json"
    installed_path = tmp_path / "installed-backend.json"
    installed = {
        "schema_version": "structural-native-installed-backend.v1",
        "backend_profile": "cpu_only",
        "device_name": "deterministic-cpu-fp64",
        "cpu_backend": 1,
        "execution_backend": 1,
        "device_id": -1,
        "cpu_backend_parity": True,
        "repeat_bitwise": True,
        "fp64": True,
        "deterministic": True,
        "fallback_count": 0,
        "operator_device_resident": False,
        "h2d_bytes": 0,
        "d2h_bytes": 0,
        "synchronization_count": 0,
        "kernel_launch_count": 0,
        "device_buffer_bytes": 0,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    installed_path.write_text(json.dumps(installed), encoding="utf-8")
    receipt["bundle_manifest_sha256"] = "sha256:" + hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    receipt["installed_backend_receipt_sha256"] = "sha256:" + hashlib.sha256(
        installed_path.read_bytes()
    ).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return subprocess.run(
        [
            "python3",
            str(CHECK),
            "--receipt",
            str(receipt_path),
            "--manifest",
            str(manifest_path),
            "--installed-backend-receipt",
            str(installed_path),
            "--require-backend",
            "cpu_only",
            "--require-authority",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def valid_contract() -> tuple[dict, dict]:
    source = "sha256:" + "a" * 64
    manifest = {
        "backend_profile": "cpu_only",
        "release_id": "cpu-0.1.0",
        "source_sha256": source,
        "execution_authority": "cpu_build_candidate",
    }
    receipt = {
        "schema_version": "structural-native-distribution-e2e.v1",
        "backend_profile": "cpu_only",
        "linkage": "shared",
        "release_id": "cpu-0.1.0",
        "source_sha256": source,
        "bundle_manifest_sha256": "sha256:" + "0" * 64,
        "installed_backend_receipt_sha256": "sha256:" + "d" * 64,
        "c2_receipt_sha256": None,
        "approved_device_runner": False,
        "single_product_abi": True,
        "python_lookup_count": 0,
        "node_lookup_count": 0,
        "install_passed": True,
        "update_passed": True,
        "rollback_passed": True,
        "package_consumer_passed": True,
        "workbench_restart_passed": True,
        "workbench_direct_parity_passed": True,
        "result_ir_sha256": "sha256:" + "b" * 64,
        "report_pdf_sha256": "sha256:" + "c" * 64,
        "fallback_count": 0,
        "authority": "hosted_cpu_c5",
    }
    return receipt, manifest


def valid_v2_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v2",
            "mgt_workbench_restart_passed": True,
            "mgt_workbench_direct_parity_passed": True,
            "mgt_source_sha256": "sha256:" + "1" * 64,
            "mgt_import_health_sha256": "sha256:" + "2" * 64,
            "mgt_result_ir_sha256": "sha256:" + "3" * 64,
            "mgt_report_pdf_sha256": "sha256:" + "4" * 64,
        }
    )
    return receipt, manifest


def valid_v3_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v2_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v3",
            "workbench_operator_surface_passed": True,
            "workbench_review_decision": "review",
            "workbench_review_sha256": "sha256:" + "5" * 64,
            "workbench_export_sha256": "sha256:" + "6" * 64,
            "mgt_workbench_operator_surface_passed": True,
            "mgt_workbench_review_decision": "review",
            "mgt_workbench_review_sha256": "sha256:" + "7" * 64,
            "mgt_workbench_export_sha256": "sha256:" + "8" * 64,
        }
    )
    return receipt, manifest


def valid_v4_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v3_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v4",
            "workbench_catalog_surface_passed": True,
            "workbench_catalog_sha256": "sha256:" + "9" * 64,
            "workbench_evidence_surface_passed": True,
            "workbench_evidence_sha256": "sha256:" + "a" * 64,
        }
    )
    return receipt, manifest


def valid_v5_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v4_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v5",
            "evidence_builder_check_passed": True,
            "evidence_builder_check_sha256": "sha256:" + "b" * 64,
            "evidence_builder_build_passed": True,
            "evidence_builder_build_sha256": "sha256:" + "c" * 64,
            "evidence_builder_manifest_sha256": "sha256:" + "d" * 64,
        }
    )
    return receipt, manifest


def valid_v6_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v5_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v6",
            "catalog_builder_check_passed": True,
            "catalog_builder_check_sha256": "sha256:" + "e" * 64,
            "catalog_builder_build_passed": True,
            "catalog_builder_build_sha256": "sha256:" + "f" * 64,
            "catalog_builder_output_sha256": "sha256:" + "0" * 64,
        }
    )
    return receipt, manifest


def valid_v7_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v6_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v7",
            "workbench_localized_pdf_surface_passed": True,
            "workbench_localized_pdf_en_us_sha256": "sha256:" + "1" * 64,
            "workbench_localized_pdf_ko_kr_sha256": "sha256:" + "2" * 64,
            "workbench_localized_pdf_en_us_receipt_sha256": "sha256:" + "3" * 64,
            "workbench_localized_pdf_ko_kr_receipt_sha256": "sha256:" + "4" * 64,
            "localized_report_font_sha256": "sha256:" + "5" * 64,
            "localized_report_font_license_sha256": "sha256:" + "6" * 64,
            "localized_report_font_provenance_sha256": "sha256:" + "7" * 64,
        }
    )
    return receipt, manifest


def valid_v8_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v7_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v8",
            "workbench_model_view_surface_passed": True,
            "workbench_model_view_isometric_sha256": "sha256:" + "8" * 64,
            "workbench_model_view_xy_sha256": "sha256:" + "9" * 64,
            "workbench_model_view_xz_sha256": "sha256:" + "a" * 64,
            "workbench_model_view_yz_sha256": "sha256:" + "b" * 64,
        }
    )
    return receipt, manifest


def valid_v9_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v8_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v9",
            "workbench_model_edit_surface_passed": True,
            "workbench_model_edit_model_sha256": "sha256:" + "c" * 64,
            "workbench_model_edit_receipt_sha256": "sha256:" + "d" * 64,
        }
    )
    return receipt, manifest


def valid_v10_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v9_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v10",
            "workbench_result_view_surface_passed": True,
            "workbench_result_view_top_displacement_sha256": "sha256:" + "e" * 64,
            "workbench_result_view_drift_ratio_sha256": "sha256:" + "f" * 64,
            "workbench_result_view_base_shear_sha256": "sha256:" + "0" * 64,
            "workbench_result_view_residual_inf_sha256": "sha256:" + "1" * 64,
            "workbench_result_view_window_sha256": "sha256:" + "2" * 64,
        }
    )
    return receipt, manifest


def valid_v11_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v10_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v11",
            "workbench_deformed_view_surface_passed": True,
            "workbench_deformed_view_isometric_sha256": "sha256:" + "3" * 64,
            "workbench_deformed_view_xy_sha256": "sha256:" + "4" * 64,
            "workbench_deformed_view_xz_sha256": "sha256:" + "5" * 64,
            "workbench_deformed_view_yz_sha256": "sha256:" + "6" * 64,
            "workbench_deformed_view_explicit_sha256": "sha256:" + "7" * 64,
        }
    )
    return receipt, manifest


def valid_v12_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v11_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v12",
            "workbench_localized_result_views_surface_passed": True,
            "workbench_result_view_ko_kr_sha256": "sha256:" + "8" * 64,
            "workbench_deformed_view_ko_kr_sha256": "sha256:" + "9" * 64,
        }
    )
    return receipt, manifest


def valid_v13_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v12_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v13",
            "workbench_localized_model_view_surface_passed": True,
            "workbench_model_view_ko_kr_sha256": "sha256:" + "a" * 64,
        }
    )
    return receipt, manifest


def valid_v14_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v13_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v14",
            "model_ir_linear_workbench_restart_passed": True,
            "model_ir_linear_workbench_direct_parity_passed": True,
            "model_ir_linear_workbench_operator_surface_passed": True,
            "model_ir_linear_workbench_review_decision": "review",
            "model_ir_linear_workbench_review_sha256": "sha256:" + "b" * 64,
            "model_ir_linear_workbench_export_sha256": "sha256:" + "c" * 64,
            "model_ir_linear_result_ir_sha256": "sha256:" + "d" * 64,
            "model_ir_linear_result_recovery_ir_sha256": "sha256:" + "e" * 64,
            "model_ir_linear_report_pdf_sha256": "sha256:" + "f" * 64,
            "model_ir_linear_pdf_receipt_sha256": "sha256:" + "0" * 64,
            "model_ir_linear_report_receipt_sha256": "sha256:" + "1" * 64,
        }
    )
    return receipt, manifest


def valid_v15_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v14_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v15",
            "model_ir_linear_localized_pdf_surface_passed": True,
            "model_ir_linear_localized_pdf_en_us_sha256": "sha256:" + "2" * 64,
            "model_ir_linear_localized_pdf_ko_kr_sha256": "sha256:" + "3" * 64,
            "model_ir_linear_localized_pdf_en_us_receipt_sha256": "sha256:" + "4" * 64,
            "model_ir_linear_localized_pdf_ko_kr_receipt_sha256": "sha256:" + "5" * 64,
        }
    )
    return receipt, manifest


def valid_v16_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v15_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v16",
            "mgt_model_ir_linear_workbench_restart_passed": True,
            "mgt_model_ir_linear_workbench_direct_parity_passed": True,
            "mgt_model_ir_linear_workbench_operator_surface_passed": True,
            "mgt_model_ir_linear_workbench_review_decision": "review",
            "mgt_model_ir_linear_workbench_review_sha256": "sha256:" + "6" * 64,
            "mgt_model_ir_linear_workbench_export_sha256": "sha256:" + "7" * 64,
            "mgt_model_ir_linear_source_sha256": "sha256:" + "8" * 64,
            "mgt_model_ir_linear_import_health_sha256": "sha256:" + "9" * 64,
            "mgt_model_ir_linear_result_ir_sha256": "sha256:" + "a" * 64,
            "mgt_model_ir_linear_result_recovery_ir_sha256": "sha256:" + "b" * 64,
            "mgt_model_ir_linear_report_pdf_sha256": "sha256:" + "c" * 64,
            "mgt_model_ir_linear_pdf_receipt_sha256": "sha256:" + "d" * 64,
            "mgt_model_ir_linear_report_receipt_sha256": "sha256:" + "e" * 64,
        }
    )
    return receipt, manifest


def valid_v17_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v16_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v17",
            "workbench_nodal_load_edit_surface_passed": True,
            "workbench_nodal_load_edit_model_sha256": "sha256:" + "f" * 64,
            "workbench_nodal_load_edit_receipt_sha256": "sha256:" + "0" * 64,
        }
    )
    return receipt, manifest


def valid_v18_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v17_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v18",
            "workbench_constraint_value_edit_surface_passed": True,
            "workbench_constraint_value_edit_model_sha256": "sha256:" + "1" * 64,
            "workbench_constraint_value_edit_receipt_sha256": "sha256:" + "2" * 64,
        }
    )
    return receipt, manifest


def valid_v19_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v18_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v19",
            "workbench_linear_material_edit_surface_passed": True,
            "workbench_linear_material_edit_model_sha256": "sha256:" + "3" * 64,
            "workbench_linear_material_edit_receipt_sha256": "sha256:" + "4" * 64,
            "workbench_frame_section_edit_surface_passed": True,
            "workbench_frame_section_edit_model_sha256": "sha256:" + "5" * 64,
            "workbench_frame_section_edit_receipt_sha256": "sha256:" + "6" * 64,
        }
    )
    return receipt, manifest


def valid_v20_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v19_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v20",
            "workbench_frame_element_orientation_edit_surface_passed": True,
            "workbench_frame_element_orientation_edit_model_sha256": "sha256:" + "7" * 64,
            "workbench_frame_element_orientation_edit_receipt_sha256": "sha256:" + "8" * 64,
        }
    )
    return receipt, manifest


def valid_v21_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v20_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v21",
            "workbench_element_connectivity_edit_surface_passed": True,
            "workbench_element_connectivity_edit_model_sha256": "sha256:" + "9" * 64,
            "workbench_element_connectivity_edit_receipt_sha256": "sha256:" + "a" * 64,
        }
    )
    return receipt, manifest


def valid_v22_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v21_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v22",
            "workbench_model_linear_request_create_surface_passed": True,
            "workbench_model_linear_request_create_request_sha256": "sha256:" + "b" * 64,
            "workbench_model_linear_request_create_receipt_sha256": "sha256:" + "c" * 64,
        }
    )
    return receipt, manifest


def valid_v23_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v22_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v23",
            "workbench_frame3d_member_add_surface_passed": True,
            "workbench_frame3d_member_add_model_sha256": "sha256:" + "d" * 64,
            "workbench_frame3d_member_add_receipt_sha256": "sha256:" + "e" * 64,
            "workbench_frame3d_member_add_request_sha256": "sha256:" + "f" * 64,
            "workbench_frame3d_member_add_result_ir_sha256": "sha256:" + "0" * 64,
        }
    )
    return receipt, manifest


def valid_v24_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v23_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v24",
            "workbench_nodal_load_add_surface_passed": True,
            "workbench_nodal_load_add_model_sha256": "sha256:" + "1" * 64,
            "workbench_nodal_load_add_receipt_sha256": "sha256:" + "2" * 64,
            "workbench_nodal_load_add_request_sha256": "sha256:" + "3" * 64,
            "workbench_nodal_load_add_result_ir_sha256": "sha256:" + "4" * 64,
            "workbench_nodal_load_add_recovery_sha256": "sha256:" + "5" * 64,
        }
    )
    return receipt, manifest


def valid_v25_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v24_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v25",
            "workbench_fixed_constraint_add_surface_passed": True,
            "workbench_fixed_constraint_add_model_sha256": "sha256:" + "6" * 64,
            "workbench_fixed_constraint_add_receipt_sha256": "sha256:" + "7" * 64,
            "workbench_fixed_constraint_add_request_sha256": "sha256:" + "8" * 64,
            "workbench_fixed_constraint_add_result_ir_sha256": "sha256:" + "9" * 64,
            "workbench_fixed_constraint_add_recovery_sha256": "sha256:" + "a" * 64,
        }
    )
    return receipt, manifest


def valid_v26_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v25_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v26",
            "workbench_linear_load_pattern_add_surface_passed": True,
            "workbench_linear_load_pattern_add_model_sha256": "sha256:" + "b" * 64,
            "workbench_linear_load_pattern_add_receipt_sha256": "sha256:" + "c" * 64,
            "workbench_linear_load_pattern_add_request_sha256": "sha256:" + "d" * 64,
            "workbench_linear_load_pattern_add_result_ir_sha256": "sha256:" + "e" * 64,
            "workbench_linear_load_pattern_add_recovery_sha256": "sha256:" + "f" * 64,
        }
    )
    return receipt, manifest


def valid_v27_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v26_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v27",
            "workbench_linear_material_add_surface_passed": True,
            "workbench_linear_material_add_model_sha256": "sha256:" + "0" * 64,
            "workbench_linear_material_add_receipt_sha256": "sha256:" + "1" * 64,
            "workbench_linear_material_add_composed_model_sha256": "sha256:" + "2" * 64,
            "workbench_linear_material_add_request_sha256": "sha256:" + "3" * 64,
            "workbench_linear_material_add_result_ir_sha256": "sha256:" + "4" * 64,
            "workbench_linear_material_add_recovery_sha256": "sha256:" + "5" * 64,
        }
    )
    return receipt, manifest


def valid_v28_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v27_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v28",
            "workbench_frame_section_add_surface_passed": True,
            "workbench_frame_section_add_model_sha256": "sha256:" + "6" * 64,
            "workbench_frame_section_add_receipt_sha256": "sha256:" + "7" * 64,
            "workbench_frame_section_add_composed_model_sha256": "sha256:" + "8" * 64,
            "workbench_frame_section_add_request_sha256": "sha256:" + "9" * 64,
            "workbench_frame_section_add_result_ir_sha256": "sha256:" + "a" * 64,
            "workbench_frame_section_add_recovery_sha256": "sha256:" + "b" * 64,
        }
    )
    return receipt, manifest


def valid_v29_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v28_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v29",
            "workbench_frame_element_properties_edit_surface_passed": True,
            "workbench_frame_element_properties_edit_model_sha256": "sha256:" + "c" * 64,
            "workbench_frame_element_properties_edit_receipt_sha256": "sha256:" + "d" * 64,
            "workbench_frame_element_properties_edit_request_sha256": "sha256:" + "e" * 64,
            "workbench_frame_element_properties_edit_result_ir_sha256": "sha256:" + "f" * 64,
            "workbench_frame_element_properties_edit_recovery_sha256": "sha256:" + "0" * 64,
        }
    )
    return receipt, manifest


def valid_v30_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v29_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v30",
            "workbench_truss3d_authoring_surface_passed": True,
            "workbench_truss3d_authoring_section_model_sha256": "sha256:" + "1" * 64,
            "workbench_truss3d_authoring_section_receipt_sha256": "sha256:" + "2" * 64,
            "workbench_truss3d_authoring_member_model_sha256": "sha256:" + "3" * 64,
            "workbench_truss3d_authoring_member_receipt_sha256": "sha256:" + "4" * 64,
            "workbench_truss3d_authoring_composed_model_sha256": "sha256:" + "5" * 64,
            "workbench_truss3d_authoring_request_sha256": "sha256:" + "6" * 64,
            "workbench_truss3d_authoring_result_ir_sha256": "sha256:" + "7" * 64,
            "workbench_truss3d_authoring_recovery_sha256": "sha256:" + "8" * 64,
        }
    )
    return receipt, manifest


def valid_v31_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v30_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v31",
            "workbench_truss3d_editing_surface_passed": True,
            "workbench_truss3d_editing_section_model_sha256": "sha256:" + "9" * 64,
            "workbench_truss3d_editing_section_receipt_sha256": "sha256:" + "a" * 64,
            "workbench_truss3d_editing_properties_model_sha256": "sha256:" + "b" * 64,
            "workbench_truss3d_editing_properties_receipt_sha256": "sha256:" + "c" * 64,
            "workbench_truss3d_editing_section_result_ir_sha256": "sha256:" + "d" * 64,
            "workbench_truss3d_editing_request_sha256": "sha256:" + "e" * 64,
            "workbench_truss3d_editing_result_ir_sha256": "sha256:" + "f" * 64,
            "workbench_truss3d_editing_recovery_sha256": "sha256:" + "0" * 64,
        }
    )
    return receipt, manifest


def valid_v32_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v31_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v32",
            "workbench_truss3d_leaf_deletion_surface_passed": True,
            "workbench_truss3d_leaf_deletion_model_sha256": "sha256:" + "1" * 64,
            "workbench_truss3d_leaf_deletion_receipt_sha256": "sha256:" + "2" * 64,
            "workbench_truss3d_leaf_deletion_request_sha256": "sha256:" + "3" * 64,
            "workbench_truss3d_leaf_deletion_result_ir_sha256": "sha256:" + "4" * 64,
            "workbench_truss3d_leaf_deletion_recovery_sha256": "sha256:" + "5" * 64,
        }
    )
    return receipt, manifest


def valid_v33_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v32_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v33",
            "workbench_frame3d_leaf_deletion_surface_passed": True,
            "workbench_frame3d_leaf_deletion_model_sha256": "sha256:" + "6" * 64,
            "workbench_frame3d_leaf_deletion_receipt_sha256": "sha256:" + "7" * 64,
            "workbench_frame3d_leaf_deletion_request_sha256": "sha256:" + "8" * 64,
            "workbench_frame3d_leaf_deletion_result_ir_sha256": "sha256:" + "9" * 64,
            "workbench_frame3d_leaf_deletion_recovery_sha256": "sha256:" + "a" * 64,
        }
    )
    return receipt, manifest


def valid_v34_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v33_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v34",
            "workbench_fixed_constraint_delete_surface_passed": True,
            "workbench_fixed_constraint_delete_model_sha256": "sha256:" + "b" * 64,
            "workbench_fixed_constraint_delete_receipt_sha256": "sha256:" + "c" * 64,
            "workbench_fixed_constraint_delete_request_sha256": "sha256:" + "d" * 64,
            "workbench_fixed_constraint_delete_result_ir_sha256": "sha256:" + "e" * 64,
            "workbench_fixed_constraint_delete_recovery_sha256": "sha256:" + "f" * 64,
        }
    )
    return receipt, manifest


def valid_v35_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v34_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v35",
            "workbench_nodal_load_delete_surface_passed": True,
            "workbench_nodal_load_delete_model_sha256": "sha256:" + "1" * 64,
            "workbench_nodal_load_delete_receipt_sha256": "sha256:" + "2" * 64,
            "workbench_nodal_load_delete_request_sha256": "sha256:" + "3" * 64,
            "workbench_nodal_load_delete_result_ir_sha256": "sha256:" + "4" * 64,
            "workbench_nodal_load_delete_recovery_sha256": "sha256:" + "5" * 64,
        }
    )
    return receipt, manifest


def valid_v36_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v35_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v36",
            "workbench_linear_load_pattern_delete_surface_passed": True,
            "workbench_linear_load_pattern_delete_model_sha256": "sha256:" + "6" * 64,
            "workbench_linear_load_pattern_delete_receipt_sha256": "sha256:" + "7" * 64,
            "workbench_linear_load_pattern_delete_request_sha256": "sha256:" + "8" * 64,
            "workbench_linear_load_pattern_delete_result_ir_sha256": "sha256:" + "9" * 64,
            "workbench_linear_load_pattern_delete_recovery_sha256": "sha256:" + "a" * 64,
        }
    )
    return receipt, manifest


def valid_v37_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v36_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v37",
            "workbench_linear_material_delete_surface_passed": True,
            "workbench_linear_material_delete_model_sha256": "sha256:" + "b" * 64,
            "workbench_linear_material_delete_receipt_sha256": "sha256:" + "c" * 64,
            "workbench_linear_material_delete_request_sha256": "sha256:" + "d" * 64,
            "workbench_linear_material_delete_result_ir_sha256": "sha256:" + "e" * 64,
            "workbench_linear_material_delete_recovery_sha256": "sha256:" + "f" * 64,
        }
    )
    return receipt, manifest


def valid_v38_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v37_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v38",
            "workbench_frame_section_delete_surface_passed": True,
            "workbench_frame_section_delete_model_sha256": "sha256:" + "1" * 64,
            "workbench_frame_section_delete_receipt_sha256": "sha256:" + "2" * 64,
            "workbench_frame_section_delete_request_sha256": "sha256:" + "3" * 64,
            "workbench_frame_section_delete_result_ir_sha256": "sha256:" + "4" * 64,
            "workbench_frame_section_delete_recovery_sha256": "sha256:" + "5" * 64,
        }
    )
    return receipt, manifest


def valid_v39_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v38_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v39",
            "workbench_truss_section_delete_surface_passed": True,
            "workbench_truss_section_delete_model_sha256": "sha256:" + "6" * 64,
            "workbench_truss_section_delete_receipt_sha256": "sha256:" + "7" * 64,
            "workbench_truss_section_delete_request_sha256": "sha256:" + "8" * 64,
            "workbench_truss_section_delete_result_ir_sha256": "sha256:" + "9" * 64,
            "workbench_truss_section_delete_recovery_sha256": "sha256:" + "a" * 64,
        }
    )
    return receipt, manifest


def valid_v40_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v39_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v40",
            "workbench_node_add_surface_passed": True,
            "workbench_node_add_model_sha256": "sha256:" + "b" * 64,
            "workbench_node_add_receipt_sha256": "sha256:" + "c" * 64,
            "workbench_node_add_composed_model_sha256": "sha256:" + "d" * 64,
            "workbench_node_add_request_sha256": "sha256:" + "e" * 64,
            "workbench_node_add_result_ir_sha256": "sha256:" + "f" * 64,
            "workbench_node_add_recovery_sha256": "sha256:" + "0" * 64,
        }
    )
    return receipt, manifest


def test_distribution_receipt_accepts_exact_hosted_cpu_contract(tmp_path: Path):
    receipt, manifest = valid_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_accepts_mgt_workbench_v2_contract(tmp_path: Path):
    receipt, manifest = valid_v2_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_accepts_operator_surface_v3_contract(tmp_path: Path):
    receipt, manifest = valid_v3_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_promoting_v3_review_decision(tmp_path: Path):
    receipt, manifest = valid_v3_contract()
    receipt["workbench_review_decision"] = "pass"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("workbench_review_decision" in error for error in validation["errors"])


def test_distribution_receipt_accepts_catalog_and_evidence_v4_contract(tmp_path: Path):
    receipt, manifest = valid_v4_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v4_catalog_authority(tmp_path: Path):
    receipt, manifest = valid_v4_contract()
    receipt["workbench_catalog_surface_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("workbench_catalog_surface_passed" in error for error in validation["errors"])


def test_distribution_receipt_accepts_native_evidence_builder_v5_contract(tmp_path: Path):
    receipt, manifest = valid_v5_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v5_builder_authority(tmp_path: Path):
    receipt, manifest = valid_v5_contract()
    receipt["evidence_builder_build_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("evidence_builder_build_passed" in error for error in validation["errors"])


def test_distribution_receipt_accepts_native_catalog_builder_v6_contract(tmp_path: Path):
    receipt, manifest = valid_v6_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v6_catalog_authority(tmp_path: Path):
    receipt, manifest = valid_v6_contract()
    receipt["catalog_builder_check_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("catalog_builder_check_passed" in error for error in validation["errors"])


def test_distribution_receipt_accepts_localized_pdf_v7_contract(tmp_path: Path):
    receipt, manifest = valid_v7_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v7_localized_pdf_authority(tmp_path: Path):
    receipt, manifest = valid_v7_contract()
    receipt["workbench_localized_pdf_surface_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_localized_pdf_surface_passed" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_equal_v7_locale_pdf_identities(tmp_path: Path):
    receipt, manifest = valid_v7_contract()
    receipt["workbench_localized_pdf_ko_kr_sha256"] = receipt[
        "workbench_localized_pdf_en_us_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("PDF identities must differ" in error for error in validation["errors"])


def test_distribution_receipt_accepts_model_topology_view_v8_contract(tmp_path: Path):
    receipt, manifest = valid_v8_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v8_model_view_authority(tmp_path: Path):
    receipt, manifest = valid_v8_contract()
    receipt["workbench_model_view_surface_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_model_view_surface_passed" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_duplicate_v8_projection_identity(tmp_path: Path):
    receipt, manifest = valid_v8_contract()
    receipt["workbench_model_view_yz_sha256"] = receipt[
        "workbench_model_view_xz_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model topology projection identities must differ" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_model_node_edit_v9_contract(tmp_path: Path):
    receipt, manifest = valid_v9_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v9_model_edit_authority(tmp_path: Path):
    receipt, manifest = valid_v9_contract()
    receipt["workbench_model_edit_surface_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_model_edit_surface_passed" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_invalid_v9_model_edit_identity(tmp_path: Path):
    receipt, manifest = valid_v9_contract()
    receipt["workbench_model_edit_receipt_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_model_edit_receipt_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_ndtha_response_view_v10_contract(tmp_path: Path):
    receipt, manifest = valid_v10_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v10_response_view_authority(
    tmp_path: Path,
):
    receipt, manifest = valid_v10_contract()
    receipt["workbench_result_view_surface_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_result_view_surface_passed" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_duplicate_v10_response_identity(tmp_path: Path):
    receipt, manifest = valid_v10_contract()
    receipt["workbench_result_view_window_sha256"] = receipt[
        "workbench_result_view_drift_ratio_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "response channel and explicit-window identities must differ" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_deformed_shape_view_v11_contract(tmp_path: Path):
    receipt, manifest = valid_v11_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v11_deformed_view_authority(
    tmp_path: Path,
):
    receipt, manifest = valid_v11_contract()
    receipt["workbench_deformed_view_surface_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_deformed_view_surface_passed" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_duplicate_v11_deformed_identity(tmp_path: Path):
    receipt, manifest = valid_v11_contract()
    receipt["workbench_deformed_view_explicit_sha256"] = receipt[
        "workbench_deformed_view_xz_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "deformed-shape projection and explicit identities must differ" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_localized_result_views_v12_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v12_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v12_localized_view_authority(
    tmp_path: Path,
):
    receipt, manifest = valid_v12_contract()
    receipt["workbench_localized_result_views_surface_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_localized_result_views_surface_passed" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_duplicate_v12_localized_view_identity(
    tmp_path: Path,
):
    receipt, manifest = valid_v12_contract()
    receipt["workbench_result_view_ko_kr_sha256"] = receipt[
        "workbench_result_view_top_displacement_sha256"
    ]
    receipt["workbench_deformed_view_ko_kr_sha256"] = receipt[
        "workbench_deformed_view_isometric_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("response-view identities must differ" in error for error in validation["errors"])
    assert any("deformed-view identities must differ" in error for error in validation["errors"])


def test_distribution_receipt_accepts_localized_model_view_v13_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v13_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v13_localized_model_view_authority(
    tmp_path: Path,
):
    receipt, manifest = valid_v13_contract()
    receipt["workbench_localized_model_view_surface_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_localized_model_view_surface_passed" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_duplicate_v13_localized_model_view_identity(
    tmp_path: Path,
):
    receipt, manifest = valid_v13_contract()
    receipt["workbench_model_view_ko_kr_sha256"] = receipt[
        "workbench_model_view_isometric_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("model-view identities must differ" in error for error in validation["errors"])


def test_distribution_receipt_accepts_model_ir_linear_workbench_v14_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v14_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v14_linear_workbench_authority(
    tmp_path: Path,
):
    receipt, manifest = valid_v14_contract()
    receipt["model_ir_linear_workbench_direct_parity_passed"] = False
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_linear_workbench_direct_parity_passed" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_promoting_or_unbound_v14_linear_report(
    tmp_path: Path,
):
    receipt, manifest = valid_v14_contract()
    receipt["model_ir_linear_workbench_review_decision"] = "pass"
    receipt["model_ir_linear_report_pdf_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_linear_workbench_review_decision" in error
        for error in validation["errors"]
    )
    assert any(
        "model_ir_linear_report_pdf_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_model_ir_linear_localized_pdf_v15_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v15_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v15_linear_localized_pdf(
    tmp_path: Path,
):
    receipt, manifest = valid_v15_contract()
    receipt["model_ir_linear_localized_pdf_surface_passed"] = False
    receipt["model_ir_linear_localized_pdf_ko_kr_sha256"] = receipt[
        "model_ir_linear_localized_pdf_en_us_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_linear_localized_pdf_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "localized en-US and ko-KR PDF identities must differ" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_mgt_model_ir_linear_workbench_v16_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v16_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v16_mgt_model_ir_linear_workbench(
    tmp_path: Path,
):
    receipt, manifest = valid_v16_contract()
    receipt["mgt_model_ir_linear_workbench_restart_passed"] = False
    receipt["mgt_model_ir_linear_workbench_review_decision"] = "pass"
    receipt["mgt_model_ir_linear_import_health_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "mgt_model_ir_linear_workbench_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "mgt_model_ir_linear_workbench_review_decision" in error
        for error in validation["errors"]
    )
    assert any(
        "mgt_model_ir_linear_import_health_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nodal_load_edit_v17_contract(tmp_path: Path):
    receipt, manifest = valid_v17_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v17_nodal_load_edit(tmp_path: Path):
    receipt, manifest = valid_v17_contract()
    receipt["workbench_nodal_load_edit_surface_passed"] = False
    receipt["workbench_nodal_load_edit_receipt_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nodal_load_edit_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nodal_load_edit_receipt_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_constraint_value_edit_v18_contract(tmp_path: Path):
    receipt, manifest = valid_v18_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v18_constraint_value_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v18_contract()
    receipt["workbench_constraint_value_edit_surface_passed"] = False
    receipt["workbench_constraint_value_edit_model_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_constraint_value_edit_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_constraint_value_edit_model_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_property_edits_v19_contract(tmp_path: Path):
    receipt, manifest = valid_v19_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v19_property_edits(tmp_path: Path):
    receipt, manifest = valid_v19_contract()
    receipt["workbench_linear_material_edit_surface_passed"] = False
    receipt["workbench_frame_section_edit_receipt_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_material_edit_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_frame_section_edit_receipt_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame_element_orientation_edit_v20_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v20_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v20_frame_element_orientation_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v20_contract()
    receipt["workbench_frame_element_orientation_edit_surface_passed"] = False
    receipt["workbench_frame_element_orientation_edit_model_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_frame_element_orientation_edit_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_frame_element_orientation_edit_model_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_element_connectivity_edit_v21_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v21_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v21_element_connectivity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v21_contract()
    receipt["workbench_element_connectivity_edit_surface_passed"] = False
    receipt["workbench_element_connectivity_edit_receipt_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_element_connectivity_edit_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_element_connectivity_edit_receipt_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_model_linear_request_create_v22_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v22_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v22_model_linear_request_create(
    tmp_path: Path,
):
    receipt, manifest = valid_v22_contract()
    receipt["workbench_model_linear_request_create_surface_passed"] = False
    receipt["workbench_model_linear_request_create_request_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_model_linear_request_create_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_model_linear_request_create_request_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame3d_member_add_v23_contract(tmp_path: Path):
    receipt, manifest = valid_v23_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v23_frame3d_member_add(
    tmp_path: Path,
):
    receipt, manifest = valid_v23_contract()
    receipt["workbench_frame3d_member_add_surface_passed"] = False
    receipt["workbench_frame3d_member_add_result_ir_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_frame3d_member_add_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_frame3d_member_add_result_ir_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nodal_load_add_v24_contract(tmp_path: Path):
    receipt, manifest = valid_v24_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v24_nodal_load_add(tmp_path: Path):
    receipt, manifest = valid_v24_contract()
    receipt["workbench_nodal_load_add_surface_passed"] = False
    receipt["workbench_nodal_load_add_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nodal_load_add_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nodal_load_add_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_fixed_constraint_add_v25_contract(tmp_path: Path):
    receipt, manifest = valid_v25_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v25_fixed_constraint_add(tmp_path: Path):
    receipt, manifest = valid_v25_contract()
    receipt["workbench_fixed_constraint_add_surface_passed"] = False
    receipt["workbench_fixed_constraint_add_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_fixed_constraint_add_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_fixed_constraint_add_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_load_pattern_add_v26_contract(tmp_path: Path):
    receipt, manifest = valid_v26_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v26_linear_load_pattern_add(tmp_path: Path):
    receipt, manifest = valid_v26_contract()
    receipt["workbench_linear_load_pattern_add_surface_passed"] = False
    receipt["workbench_linear_load_pattern_add_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_load_pattern_add_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_load_pattern_add_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_material_add_v27_contract(tmp_path: Path):
    receipt, manifest = valid_v27_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v27_linear_material_add(tmp_path: Path):
    receipt, manifest = valid_v27_contract()
    receipt["workbench_linear_material_add_surface_passed"] = False
    receipt["workbench_linear_material_add_composed_model_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_material_add_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_material_add_composed_model_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame_section_add_v28_contract(tmp_path: Path):
    receipt, manifest = valid_v28_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v28_frame_section_add(tmp_path: Path):
    receipt, manifest = valid_v28_contract()
    receipt["workbench_frame_section_add_surface_passed"] = False
    receipt["workbench_frame_section_add_composed_model_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_frame_section_add_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_frame_section_add_composed_model_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame_element_properties_v29_contract(tmp_path: Path):
    receipt, manifest = valid_v29_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v29_frame_element_properties(tmp_path: Path):
    receipt, manifest = valid_v29_contract()
    receipt["workbench_frame_element_properties_edit_surface_passed"] = False
    receipt["workbench_frame_element_properties_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_frame_element_properties_edit_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_frame_element_properties_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_truss3d_authoring_v30_contract(tmp_path: Path):
    receipt, manifest = valid_v30_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v30_truss3d_authoring(tmp_path: Path):
    receipt, manifest = valid_v30_contract()
    receipt["workbench_truss3d_authoring_surface_passed"] = False
    receipt["workbench_truss3d_authoring_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_truss3d_authoring_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_truss3d_authoring_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_truss3d_editing_v31_contract(tmp_path: Path):
    receipt, manifest = valid_v31_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v31_truss3d_editing(tmp_path: Path):
    receipt, manifest = valid_v31_contract()
    receipt["workbench_truss3d_editing_surface_passed"] = False
    receipt["workbench_truss3d_editing_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_truss3d_editing_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_truss3d_editing_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_truss3d_leaf_deletion_v32_contract(tmp_path: Path):
    receipt, manifest = valid_v32_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v32_truss3d_leaf_deletion(
    tmp_path: Path,
):
    receipt, manifest = valid_v32_contract()
    receipt["workbench_truss3d_leaf_deletion_surface_passed"] = False
    receipt["workbench_truss3d_leaf_deletion_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_truss3d_leaf_deletion_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_truss3d_leaf_deletion_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame3d_leaf_deletion_v33_contract(tmp_path: Path):
    receipt, manifest = valid_v33_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v33_frame3d_leaf_deletion(
    tmp_path: Path,
):
    receipt, manifest = valid_v33_contract()
    receipt["workbench_frame3d_leaf_deletion_surface_passed"] = False
    receipt["workbench_frame3d_leaf_deletion_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_frame3d_leaf_deletion_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_frame3d_leaf_deletion_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_fixed_constraint_delete_v34_contract(tmp_path: Path):
    receipt, manifest = valid_v34_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v34_fixed_constraint_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v34_contract()
    receipt["workbench_fixed_constraint_delete_surface_passed"] = False
    receipt["workbench_fixed_constraint_delete_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_fixed_constraint_delete_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_fixed_constraint_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nodal_load_delete_v35_contract(tmp_path: Path):
    receipt, manifest = valid_v35_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v35_nodal_load_delete(tmp_path: Path):
    receipt, manifest = valid_v35_contract()
    receipt["workbench_nodal_load_delete_surface_passed"] = False
    receipt["workbench_nodal_load_delete_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nodal_load_delete_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nodal_load_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_load_pattern_delete_v36_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v36_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v36_linear_load_pattern_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v36_contract()
    receipt["workbench_linear_load_pattern_delete_surface_passed"] = False
    receipt["workbench_linear_load_pattern_delete_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_load_pattern_delete_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_load_pattern_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_material_delete_v37_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v37_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v37_linear_material_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v37_contract()
    receipt["workbench_linear_material_delete_surface_passed"] = False
    receipt["workbench_linear_material_delete_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_material_delete_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_material_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame_section_delete_v38_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v38_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v38_frame_section_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v38_contract()
    receipt["workbench_frame_section_delete_surface_passed"] = False
    receipt["workbench_frame_section_delete_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_frame_section_delete_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_frame_section_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_truss_section_delete_v39_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v39_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v39_truss_section_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v39_contract()
    receipt["workbench_truss_section_delete_surface_passed"] = False
    receipt["workbench_truss_section_delete_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_truss_section_delete_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_truss_section_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_node_add_v40_contract(tmp_path: Path):
    receipt, manifest = valid_v40_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v40_node_add(tmp_path: Path):
    receipt, manifest = valid_v40_contract()
    receipt["workbench_node_add_surface_passed"] = False
    receipt["workbench_node_add_composed_model_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_node_add_surface_passed" in error for error in validation["errors"]
    )
    assert any(
        "workbench_node_add_composed_model_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_runtime_and_manifest_drift(tmp_path: Path):
    receipt, manifest = valid_contract()
    receipt["node_lookup_count"] = 1
    receipt["single_product_abi"] = False
    manifest["release_id"] = "different"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert validation["valid"] is False
    assert any("node_lookup_count" in error for error in validation["errors"])
    assert any("single_product_abi" in error for error in validation["errors"])
    assert any("release" in error for error in validation["errors"])


def test_distribution_implementation_has_durable_and_fail_closed_boundaries():
    source = LIB.read_text(encoding="utf-8")
    for token in (
        "structural-distribution.v1",
        "structural-install-transaction.v1",
        "structural-native-rootfs-isolation-e2e.v6",
        "model_ir_linear_result_recovery_ir_sha256",
        "model_ir_linear_pdf_receipt_sha256",
        "model_ir_linear_localized_pdf_surface_passed",
        "model_ir_linear_localized_pdf_en_us_sha256",
        "mgt_model_ir_linear_source_sha256",
        "mgt_model_ir_linear_import_health_sha256",
        "mgt_model_ir_linear_result_recovery_ir_sha256",
        "lock_exclusive",
        "sync_all",
        "release_id_immutable",
        "bundle_payload_hash_mismatch",
        "recovery_required",
        "AfterPrepared",
        "AfterMaterialized",
        "AfterActivated",
    ):
        assert token in source


def test_build_and_e2e_scripts_enforce_split_native_packages():
    build = BUILD.read_text(encoding="utf-8")
    catalog_wrapper = (ROOT / "scripts/build_native_benchmark_catalog.sh").read_text(
        encoding="utf-8"
    )
    evidence_wrapper = (
        ROOT / "scripts/build_native_workbench_evidence_bundle.sh"
    ).read_text(encoding="utf-8")
    e2e = RUN.read_text(encoding="utf-8")
    rocm_e2e = RUN_ROCM.read_text(encoding="utf-8")
    rootfs_e2e = ROOTFS_RUN.read_text(encoding="utf-8")
    ffi = FFI_BUILD.read_text(encoding="utf-8")
    assert 'STRUCTURAL_ENABLE_HIP="$enable_hip"' in build
    assert "ROCm distribution currently requires shared linkage" in build
    assert "rocm_runtime_rpath" in build
    assert "libamdhip64.so" in build
    assert '"-DCMAKE_INSTALL_RPATH=$install_rpath"' in build
    assert "STRUCTURAL_NATIVE_PREFIX" in build
    assert "cargo build --manifest-path native/Cargo.toml --release --locked" in build
    assert "-p structural-catalog" in build
    assert 'structural-catalog "$payload/bin/structural-catalog"' in build
    assert "-p structural-evidence" in build
    assert 'structural-evidence "$payload/bin/structural-evidence"' in build
    assert 'localized_report_share="$payload/share/structural-report"' in build
    assert "OFL-1.1.txt" in build
    assert "StructuralReportKoreanSubset.provenance.json" in build
    assert "StructuralReportKoreanSubset.ttf" in build
    assert '"$1" == "--check"' in evidence_wrapper
    assert "structural-evidence -- check --root" in evidence_wrapper
    assert 'if [[ "$#" -ne 0 ]]' in evidence_wrapper
    assert "structural-evidence -- build" in evidence_wrapper
    assert '"$1" == "--check"' in catalog_wrapper
    assert "structural-catalog -- check --root" in catalog_wrapper
    assert 'if [[ "$#" -ne 0 ]]' in catalog_wrapper
    assert "structural-catalog -- build" in catalog_wrapper
    assert "PATH=\"$empty_path\"" in e2e
    assert "diff -r \"$restarted\" \"$direct\"" in e2e
    assert "workflow-mgt" in e2e
    assert "diff -r \"$mgt_restarted\" \"$mgt_direct\"" in e2e
    assert "mgt_workbench_direct_parity_passed" in e2e
    assert "exercise_operator_surface" in e2e
    assert "workbench_operator_surface_passed" in e2e
    assert "structural-native-distribution-e2e.v29" in e2e
    assert "structural-native-distribution-e2e.v30" in e2e
    assert "structural-native-distribution-e2e.v31" in e2e
    assert "structural-native-distribution-e2e.v32" in e2e
    assert "structural-native-distribution-e2e.v33" in e2e
    assert "structural-native-distribution-e2e.v34" in e2e
    assert "structural-native-distribution-e2e.v35" in e2e
    assert "structural-native-distribution-e2e.v36" in e2e
    assert "structural-native-distribution-e2e.v37" in e2e
    assert "structural-native-distribution-e2e.v38" in e2e
    assert "structural-native-distribution-e2e.v39" in e2e
    assert "structural-native-distribution-e2e.v40" in e2e
    assert "exercise_model_linear_request_create_surface" in e2e
    assert "model-create-linear-analysis-request" in e2e
    assert "workbench_model_linear_request_create_surface_passed" in e2e
    assert "workbench_model_linear_request_create_request_sha256" in e2e
    assert "workbench_model_linear_request_create_receipt_sha256" in e2e
    assert "workflow-model-linear" in e2e
    assert "model_ir_linear_workbench_restart_passed" in e2e
    assert "model_ir_linear_workbench_direct_parity_passed" in e2e
    assert "model_ir_linear_workbench_operator_surface_passed" in e2e
    assert "model_ir_linear_result_recovery_ir_sha256" in e2e
    assert "model_ir_linear_report_pdf_sha256" in e2e
    assert "exercise_model_ir_linear_localized_pdf_surface" in e2e
    assert "model_ir_linear_localized_pdf_surface_passed" in e2e
    assert "structural-native-sparse-linear-localized-pdf-report-receipt.v2" in e2e
    assert "structural-native-sparse-linear-pdf-report-receipt.v1" in e2e
    assert "frame_cantilever_language_neutral_oracle_v1.txt" in e2e
    assert "workflow-mgt-model-linear" in e2e
    assert "mgt_cantilever_language_neutral_oracle_v1.txt" in e2e
    assert "mgt_model_ir_linear_workbench_restart_passed" in e2e
    assert "mgt_model_ir_linear_result_recovery_ir_sha256" in e2e
    assert "exercise_localized_pdf_surface" in e2e
    assert "report-export-pdf" in e2e
    assert "workbench_localized_pdf_surface_passed" in e2e
    assert "localized_report_font_license_sha256" in e2e
    assert "model-ir-linear-localized-pdf-en-US-first" in rootfs_e2e
    assert "--model-ir-linear-workbench-session-before-localized-pdf" in rootfs_e2e
    assert "--model-ir-linear-localized-pdf-ko-kr-second-root" in rootfs_e2e
    assert "exercise_model_view_surface" in e2e
    assert "model-view" in e2e
    assert "workbench_model_view_surface_passed" in e2e
    assert "workbench_model_view_yz_sha256" in e2e
    assert "workbench_localized_model_view_surface_passed" in e2e
    assert "workbench_model_view_ko_kr_sha256" in e2e
    assert "exercise_model_edit_surface" in e2e
    assert "model-edit-node" in e2e
    assert "workbench_model_edit_surface_passed" in e2e
    assert "workbench_model_edit_receipt_sha256" in e2e
    assert "exercise_nodal_load_edit_surface" in e2e
    assert "model-edit-nodal-load" in e2e
    assert "workbench_nodal_load_edit_surface_passed" in e2e
    assert "workbench_nodal_load_edit_receipt_sha256" in e2e
    assert "exercise_constraint_value_edit_surface" in e2e
    assert "model-edit-constraint-value" in e2e
    assert "workbench_constraint_value_edit_surface_passed" in e2e
    assert "workbench_constraint_value_edit_receipt_sha256" in e2e
    assert "exercise_linear_material_edit_surface" in e2e
    assert "model-edit-linear-material" in e2e
    assert "workbench_linear_material_edit_surface_passed" in e2e
    assert "workbench_linear_material_edit_receipt_sha256" in e2e
    assert "exercise_frame_section_edit_surface" in e2e
    assert "model-edit-frame-section" in e2e
    assert "workbench_frame_section_edit_surface_passed" in e2e
    assert "workbench_frame_section_edit_receipt_sha256" in e2e
    assert "exercise_frame_element_orientation_edit_surface" in e2e
    assert "model-edit-frame-element-orientation" in e2e
    assert "workbench_frame_element_orientation_edit_surface_passed" in e2e
    assert "workbench_frame_element_orientation_edit_receipt_sha256" in e2e
    assert "exercise_element_connectivity_edit_surface" in e2e
    assert "model-edit-element-connectivity" in e2e
    assert "workbench_element_connectivity_edit_surface_passed" in e2e
    assert "workbench_element_connectivity_edit_receipt_sha256" in e2e
    assert "exercise_frame3d_member_add_surface" in e2e
    assert "model-add-frame3d-member" in e2e
    assert "workbench_frame3d_member_add_surface_passed" in e2e
    assert "workbench_frame3d_member_add_model_sha256" in e2e
    assert "workbench_frame3d_member_add_receipt_sha256" in e2e
    assert "workbench_frame3d_member_add_request_sha256" in e2e
    assert "workbench_frame3d_member_add_result_ir_sha256" in e2e
    assert "exercise_nodal_load_add_surface" in e2e
    assert "model-add-nodal-load" in e2e
    assert "workbench_nodal_load_add_surface_passed" in e2e
    assert "workbench_nodal_load_add_model_sha256" in e2e
    assert "workbench_nodal_load_add_receipt_sha256" in e2e
    assert "workbench_nodal_load_add_request_sha256" in e2e
    assert "workbench_nodal_load_add_result_ir_sha256" in e2e
    assert "workbench_nodal_load_add_recovery_sha256" in e2e
    assert "exercise_fixed_constraint_add_surface" in e2e
    assert "model-add-fixed-constraint" in e2e
    assert "workbench_fixed_constraint_add_surface_passed" in e2e
    assert "workbench_fixed_constraint_add_model_sha256" in e2e
    assert "workbench_fixed_constraint_add_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_add_request_sha256" in e2e
    assert "workbench_fixed_constraint_add_result_ir_sha256" in e2e
    assert "workbench_fixed_constraint_add_recovery_sha256" in e2e
    assert "exercise_linear_load_pattern_add_surface" in e2e
    assert "model-add-linear-load-pattern" in e2e
    assert "workbench_linear_load_pattern_add_surface_passed" in e2e
    assert "workbench_linear_load_pattern_add_model_sha256" in e2e
    assert "workbench_linear_load_pattern_add_receipt_sha256" in e2e
    assert "workbench_linear_load_pattern_add_request_sha256" in e2e
    assert "workbench_linear_load_pattern_add_result_ir_sha256" in e2e
    assert "workbench_linear_load_pattern_add_recovery_sha256" in e2e
    assert "exercise_linear_material_add_surface" in e2e
    assert "model-add-linear-material" in e2e
    assert "workbench_linear_material_add_surface_passed" in e2e
    assert "workbench_linear_material_add_model_sha256" in e2e
    assert "workbench_linear_material_add_receipt_sha256" in e2e
    assert "workbench_linear_material_add_composed_model_sha256" in e2e
    assert "workbench_linear_material_add_request_sha256" in e2e
    assert "workbench_linear_material_add_result_ir_sha256" in e2e
    assert "workbench_linear_material_add_recovery_sha256" in e2e
    assert "exercise_frame_section_add_surface" in e2e
    assert "model-add-frame-section" in e2e
    assert "workbench_frame_section_add_surface_passed" in e2e
    assert "workbench_frame_section_add_model_sha256" in e2e
    assert "workbench_frame_section_add_receipt_sha256" in e2e
    assert "workbench_frame_section_add_composed_model_sha256" in e2e
    assert "workbench_frame_section_add_request_sha256" in e2e
    assert "workbench_frame_section_add_result_ir_sha256" in e2e
    assert "workbench_frame_section_add_recovery_sha256" in e2e
    assert "exercise_frame_element_properties_edit_surface" in e2e
    assert "model-edit-frame-element-properties" in e2e
    assert "workbench_frame_element_properties_edit_surface_passed" in e2e
    assert "workbench_frame_element_properties_edit_model_sha256" in e2e
    assert "workbench_frame_element_properties_edit_receipt_sha256" in e2e
    assert "workbench_frame_element_properties_edit_request_sha256" in e2e
    assert "workbench_frame_element_properties_edit_result_ir_sha256" in e2e
    assert "workbench_frame_element_properties_edit_recovery_sha256" in e2e
    assert "exercise_truss3d_authoring_surface" in e2e
    assert "model-add-truss-section" in e2e
    assert "model-add-truss3d-member" in e2e
    assert "workbench_truss3d_authoring_surface_passed" in e2e
    assert "workbench_truss3d_authoring_section_model_sha256" in e2e
    assert "workbench_truss3d_authoring_section_receipt_sha256" in e2e
    assert "workbench_truss3d_authoring_member_model_sha256" in e2e
    assert "workbench_truss3d_authoring_member_receipt_sha256" in e2e
    assert "workbench_truss3d_authoring_composed_model_sha256" in e2e
    assert "workbench_truss3d_authoring_request_sha256" in e2e
    assert "workbench_truss3d_authoring_result_ir_sha256" in e2e
    assert "workbench_truss3d_authoring_recovery_sha256" in e2e
    assert "exercise_truss3d_editing_surface" in e2e
    assert "model-edit-truss-section" in e2e
    assert "model-edit-truss-element-properties" in e2e
    assert "workbench_truss3d_editing_surface_passed" in e2e
    assert "workbench_truss3d_editing_section_model_sha256" in e2e
    assert "workbench_truss3d_editing_section_receipt_sha256" in e2e
    assert "workbench_truss3d_editing_properties_model_sha256" in e2e
    assert "workbench_truss3d_editing_properties_receipt_sha256" in e2e
    assert "workbench_truss3d_editing_section_result_ir_sha256" in e2e
    assert "workbench_truss3d_editing_request_sha256" in e2e
    assert "workbench_truss3d_editing_result_ir_sha256" in e2e
    assert "workbench_truss3d_editing_recovery_sha256" in e2e
    assert "exercise_truss3d_leaf_deletion_surface" in e2e
    assert "model-delete-truss3d-leaf-member" in e2e
    assert "workbench_truss3d_leaf_deletion_surface_passed" in e2e
    assert "workbench_truss3d_leaf_deletion_model_sha256" in e2e
    assert "workbench_truss3d_leaf_deletion_receipt_sha256" in e2e
    assert "workbench_truss3d_leaf_deletion_request_sha256" in e2e
    assert "workbench_truss3d_leaf_deletion_result_ir_sha256" in e2e
    assert "workbench_truss3d_leaf_deletion_recovery_sha256" in e2e
    assert "exercise_frame3d_leaf_deletion_surface" in e2e
    assert "model-delete-frame3d-leaf-member" in e2e
    assert "workbench_frame3d_leaf_deletion_surface_passed" in e2e
    assert "workbench_frame3d_leaf_deletion_model_sha256" in e2e
    assert "workbench_frame3d_leaf_deletion_receipt_sha256" in e2e
    assert "workbench_frame3d_leaf_deletion_request_sha256" in e2e
    assert "workbench_frame3d_leaf_deletion_result_ir_sha256" in e2e
    assert "workbench_frame3d_leaf_deletion_recovery_sha256" in e2e
    assert "exercise_fixed_constraint_deletion_surface" in e2e
    assert "model-delete-fixed-constraint" in e2e
    assert "workbench_fixed_constraint_delete_surface_passed" in e2e
    assert "workbench_fixed_constraint_delete_model_sha256" in e2e
    assert "workbench_fixed_constraint_delete_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_delete_request_sha256" in e2e
    assert "workbench_fixed_constraint_delete_result_ir_sha256" in e2e
    assert "workbench_fixed_constraint_delete_recovery_sha256" in e2e
    assert "exercise_nodal_load_deletion_surface" in e2e
    assert "model-delete-nodal-load" in e2e
    assert "workbench_nodal_load_delete_surface_passed" in e2e
    assert "workbench_nodal_load_delete_model_sha256" in e2e
    assert "workbench_nodal_load_delete_receipt_sha256" in e2e
    assert "workbench_nodal_load_delete_request_sha256" in e2e
    assert "workbench_nodal_load_delete_result_ir_sha256" in e2e
    assert "workbench_nodal_load_delete_recovery_sha256" in e2e
    assert "exercise_linear_load_pattern_deletion_surface" in e2e
    assert "model-delete-linear-load-pattern" in e2e
    assert "workbench_linear_load_pattern_delete_surface_passed" in e2e
    assert "workbench_linear_load_pattern_delete_model_sha256" in e2e
    assert "workbench_linear_load_pattern_delete_receipt_sha256" in e2e
    assert "workbench_linear_load_pattern_delete_request_sha256" in e2e
    assert "workbench_linear_load_pattern_delete_result_ir_sha256" in e2e
    assert "workbench_linear_load_pattern_delete_recovery_sha256" in e2e
    assert "exercise_linear_material_deletion_surface" in e2e
    assert "model-delete-linear-material" in e2e
    assert "workbench_linear_material_delete_surface_passed" in e2e
    assert "workbench_linear_material_delete_model_sha256" in e2e
    assert "workbench_linear_material_delete_receipt_sha256" in e2e
    assert "workbench_linear_material_delete_request_sha256" in e2e
    assert "workbench_linear_material_delete_result_ir_sha256" in e2e
    assert "workbench_linear_material_delete_recovery_sha256" in e2e
    assert "exercise_frame_section_deletion_surface" in e2e
    assert "model-delete-frame-section" in e2e
    assert "workbench_frame_section_delete_surface_passed" in e2e
    assert "workbench_frame_section_delete_model_sha256" in e2e
    assert "workbench_frame_section_delete_receipt_sha256" in e2e
    assert "workbench_frame_section_delete_request_sha256" in e2e
    assert "workbench_frame_section_delete_result_ir_sha256" in e2e
    assert "workbench_frame_section_delete_recovery_sha256" in e2e
    assert "exercise_truss_section_deletion_surface" in e2e
    assert "model-delete-truss-section" in e2e
    assert "workbench_truss_section_delete_surface_passed" in e2e
    assert "workbench_truss_section_delete_model_sha256" in e2e
    assert "workbench_truss_section_delete_receipt_sha256" in e2e
    assert "workbench_truss_section_delete_request_sha256" in e2e
    assert "workbench_truss_section_delete_result_ir_sha256" in e2e
    assert "workbench_truss_section_delete_recovery_sha256" in e2e
    assert "exercise_node_add_surface" in e2e
    assert "model-add-node" in e2e
    assert "workbench_node_add_surface_passed" in e2e
    assert "workbench_node_add_model_sha256" in e2e
    assert "workbench_node_add_receipt_sha256" in e2e
    assert "workbench_node_add_composed_model_sha256" in e2e
    assert "workbench_node_add_request_sha256" in e2e
    assert "workbench_node_add_result_ir_sha256" in e2e
    assert "workbench_node_add_recovery_sha256" in e2e
    assert "exercise_result_view_surface" in e2e
    assert "result-view" in e2e
    assert "workbench_result_view_surface_passed" in e2e
    assert "workbench_result_view_window_sha256" in e2e
    assert "exercise_deformed_view_surface" in e2e
    assert "result-deformed-view" in e2e
    assert "workbench_deformed_view_surface_passed" in e2e
    assert "workbench_deformed_view_explicit_sha256" in e2e
    assert "--locale ko-KR" in e2e
    assert "workbench_localized_result_views_surface_passed" in e2e
    assert "workbench_result_view_ko_kr_sha256" in e2e
    assert "workbench_deformed_view_ko_kr_sha256" in e2e
    assert "structural-catalog" in e2e
    assert "catalog_builder_build_passed" in e2e
    assert "structural-evidence" in e2e
    assert "evidence_builder_build_passed" in e2e
    assert "structural-native-benchmark-catalog-view.v1" in e2e
    assert "structural-native-evidence-bundle-view.v1" in e2e
    assert "workbench_catalog_surface_passed" in e2e
    assert "workbench_evidence_surface_passed" in e2e
    assert "update --bundle" in e2e
    assert "rollback --root" in e2e
    assert "single_product_abi" in e2e
    assert "python_lookup_count" in e2e
    assert "STRUCTURAL_NATIVE_PREFIX" in ffi
    assert "rustc-link-lib=dylib=structural_c_abi_v1" in ffi
    assert "native-hip-approved" in rocm_e2e
    assert "ROCm product library has an unresolved runtime dependency" in rocm_e2e
    assert "structural_native_backend_package_consumer\" hip" in rocm_e2e
    assert "workflow-mgt" in rocm_e2e
    assert "mgt_workbench_direct_parity_passed" in rocm_e2e
    assert "exercise_operator_surface" in rocm_e2e
    assert "workbench_operator_surface_passed" in rocm_e2e
    assert "structural-native-distribution-e2e.v13" in rocm_e2e
    assert "exercise_localized_pdf_surface" in rocm_e2e
    assert "report-export-pdf" in rocm_e2e
    assert "workbench_localized_pdf_surface_passed" in rocm_e2e
    assert "localized_report_font_license_sha256" in rocm_e2e
    assert "exercise_model_view_surface" in rocm_e2e
    assert "model-view" in rocm_e2e
    assert "workbench_model_view_surface_passed" in rocm_e2e
    assert "workbench_model_view_yz_sha256" in rocm_e2e
    assert "workbench_localized_model_view_surface_passed" in rocm_e2e
    assert "workbench_model_view_ko_kr_sha256" in rocm_e2e
    assert "exercise_model_edit_surface" in rocm_e2e
    assert "model-edit-node" in rocm_e2e
    assert "workbench_model_edit_surface_passed" in rocm_e2e
    assert "workbench_model_edit_receipt_sha256" in rocm_e2e
    assert "exercise_result_view_surface" in rocm_e2e
    assert "result-view" in rocm_e2e
    assert "workbench_result_view_surface_passed" in rocm_e2e
    assert "workbench_result_view_window_sha256" in rocm_e2e
    assert "exercise_deformed_view_surface" in rocm_e2e
    assert "result-deformed-view" in rocm_e2e
    assert "workbench_deformed_view_surface_passed" in rocm_e2e
    assert "workbench_deformed_view_explicit_sha256" in rocm_e2e
    assert "--locale ko-KR" in rocm_e2e
    assert "workbench_localized_result_views_surface_passed" in rocm_e2e
    assert "workbench_result_view_ko_kr_sha256" in rocm_e2e
    assert "workbench_deformed_view_ko_kr_sha256" in rocm_e2e
    assert "structural-catalog" in rocm_e2e
    assert "catalog_builder_build_passed" in rocm_e2e
    assert "structural-evidence" in rocm_e2e
    assert "evidence_builder_build_passed" in rocm_e2e
    assert "workbench_catalog_surface_passed" in rocm_e2e
    assert "workbench_evidence_surface_passed" in rocm_e2e
    assert '"approved_device_runner\\\":true' in rocm_e2e
    assert "inspect --workspace /mnt/modelir-workbench" in rootfs_e2e
    assert "review-show --workspace /mnt/modelir-workbench" in rootfs_e2e
    assert "export --workspace /mnt/modelir-workbench" in rootfs_e2e
    assert "inspect --workspace /mnt/mgt-workbench" in rootfs_e2e
    assert "workflow-model-linear" in rootfs_e2e
    assert "workflow-mgt-model-linear" in rootfs_e2e
    assert "inspect --workspace /mnt/model-ir-linear-workbench" in rootfs_e2e
    assert "review-show --workspace /mnt/model-ir-linear-workbench" in rootfs_e2e
    assert "export --workspace /mnt/model-ir-linear-workbench" in rootfs_e2e
    assert "--model-ir-linear-workbench-root" in rootfs_e2e
    assert "--model-ir-linear-workbench-inspect-before-review" in rootfs_e2e
    assert "--mgt-model-ir-linear-workbench-root" in rootfs_e2e
    assert "--mgt-model-ir-linear-workbench-inspect-before-review" in rootfs_e2e
    assert "mgt_cantilever_language_neutral_oracle_v1.txt" in rootfs_e2e
    assert "frame_cantilever_language_neutral_oracle_v1.txt" in rootfs_e2e
    assert "--workbench-inspect-before-review" in rootfs_e2e
    assert "--workbench-catalog" in rootfs_e2e
    assert "--workbench-evidence" in rootfs_e2e
    assert "structural-workbench catalog" in rootfs_e2e
    assert "structural-workbench evidence" in rootfs_e2e
    assert "IFS= read -r catalog_line" in rootfs_e2e
    assert "IFS= read -r evidence_line" in rootfs_e2e
    assert "grep -Fq" not in rootfs_e2e
    assert "runtime-receipt-verify" in rootfs_e2e
