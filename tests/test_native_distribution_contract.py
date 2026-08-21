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


def run_checker(
    tmp_path: Path, receipt: dict, manifest: dict
) -> subprocess.CompletedProcess[str]:
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
    receipt["bundle_manifest_sha256"] = (
        "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )
    receipt["installed_backend_receipt_sha256"] = (
        "sha256:" + hashlib.sha256(installed_path.read_bytes()).hexdigest()
    )
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
            "workbench_frame_element_orientation_edit_model_sha256": "sha256:"
            + "7" * 64,
            "workbench_frame_element_orientation_edit_receipt_sha256": "sha256:"
            + "8" * 64,
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
            "workbench_model_linear_request_create_request_sha256": "sha256:"
            + "b" * 64,
            "workbench_model_linear_request_create_receipt_sha256": "sha256:"
            + "c" * 64,
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
            "workbench_frame_element_properties_edit_model_sha256": "sha256:"
            + "c" * 64,
            "workbench_frame_element_properties_edit_receipt_sha256": "sha256:"
            + "d" * 64,
            "workbench_frame_element_properties_edit_request_sha256": "sha256:"
            + "e" * 64,
            "workbench_frame_element_properties_edit_result_ir_sha256": "sha256:"
            + "f" * 64,
            "workbench_frame_element_properties_edit_recovery_sha256": "sha256:"
            + "0" * 64,
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
            "workbench_linear_load_pattern_delete_result_ir_sha256": "sha256:"
            + "9" * 64,
            "workbench_linear_load_pattern_delete_recovery_sha256": "sha256:"
            + "a" * 64,
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


def valid_v41_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v40_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v41",
            "workbench_orphan_node_delete_surface_passed": True,
            "workbench_orphan_node_delete_model_sha256": "sha256:" + "1" * 64,
            "workbench_orphan_node_delete_receipt_sha256": "sha256:" + "2" * 64,
            "workbench_orphan_node_delete_request_sha256": "sha256:" + "3" * 64,
            "workbench_orphan_node_delete_result_ir_sha256": "sha256:" + "4" * 64,
            "workbench_orphan_node_delete_recovery_sha256": "sha256:" + "5" * 64,
        }
    )
    return receipt, manifest


def valid_v42_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v41_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v42",
            "workbench_linear_load_combination_add_surface_passed": True,
            "workbench_linear_load_combination_add_model_sha256": "sha256:" + "6" * 64,
            "workbench_linear_load_combination_add_receipt_sha256": "sha256:"
            + "7" * 64,
            "workbench_linear_load_combination_add_validation_sha256": "sha256:"
            + "8" * 64,
            "workbench_linear_load_combination_add_view_sha256": "sha256:" + "9" * 64,
            "workbench_linear_load_combination_add_solver_rejection_sha256": "sha256:"
            + "a" * 64,
        }
    )
    return receipt, manifest


def valid_v43_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v42_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v43",
            "workbench_linear_load_combination_delete_surface_passed": True,
            "workbench_linear_load_combination_delete_model_sha256": "sha256:"
            + "b" * 64,
            "workbench_linear_load_combination_delete_receipt_sha256": "sha256:"
            + "c" * 64,
            "workbench_linear_load_combination_delete_request_sha256": "sha256:"
            + "d" * 64,
            "workbench_linear_load_combination_delete_result_ir_sha256": "sha256:"
            + "e" * 64,
            "workbench_linear_load_combination_delete_recovery_sha256": "sha256:"
            + "f" * 64,
        }
    )
    return receipt, manifest


def valid_v44_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v43_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v44",
            "workbench_linear_load_combination_execution_surface_passed": True,
            "workbench_linear_load_combination_request_receipt_sha256": "sha256:"
            + "0" * 64,
            "workbench_linear_load_combination_request_sha256": "sha256:" + "1" * 64,
            "workbench_linear_load_combination_assembly_receipt_sha256": "sha256:"
            + "2" * 64,
            "workbench_linear_load_combination_checkpoint_sha256": "sha256:" + "3" * 64,
            "workbench_linear_load_combination_result_ir_sha256": "sha256:" + "4" * 64,
            "workbench_linear_load_combination_recovery_sha256": "sha256:" + "5" * 64,
            "workbench_linear_load_combination_report_ir_sha256": "sha256:" + "6" * 64,
            "workbench_linear_load_combination_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v45_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v44_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v45",
            "workbench_direct_linear_load_combination_surface_passed": True,
            "workbench_direct_linear_load_combination_model_sha256": "sha256:"
            + "7" * 64,
            "workbench_direct_linear_load_combination_edit_receipt_sha256": "sha256:"
            + "8" * 64,
            "workbench_direct_linear_load_combination_request_receipt_sha256": "sha256:"
            + "9" * 64,
            "workbench_direct_linear_load_combination_request_sha256": "sha256:"
            + "a" * 64,
            "workbench_direct_linear_load_combination_assembly_receipt_sha256": "sha256:"
            + "b" * 64,
            "workbench_direct_linear_load_combination_checkpoint_sha256": "sha256:"
            + "c" * 64,
            "workbench_direct_linear_load_combination_result_ir_sha256": "sha256:"
            + "d" * 64,
            "workbench_direct_linear_load_combination_recovery_sha256": "sha256:"
            + "e" * 64,
            "workbench_direct_linear_load_combination_report_ir_sha256": "sha256:"
            + "f" * 64,
            "workbench_direct_linear_load_combination_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v46_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v45_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v46",
            "workbench_nested_linear_load_combination_surface_passed": True,
            "workbench_nested_linear_load_combination_model_sha256": "sha256:"
            + "0" * 64,
            "workbench_nested_linear_load_combination_edit_receipt_sha256": "sha256:"
            + "1" * 64,
            "workbench_nested_linear_load_combination_request_receipt_sha256": "sha256:"
            + "2" * 64,
            "workbench_nested_linear_load_combination_request_sha256": "sha256:"
            + "3" * 64,
            "workbench_nested_linear_load_combination_assembly_receipt_sha256": "sha256:"
            + "4" * 64,
            "workbench_nested_linear_load_combination_checkpoint_sha256": "sha256:"
            + "5" * 64,
            "workbench_nested_linear_load_combination_result_ir_sha256": "sha256:"
            + "6" * 64,
            "workbench_nested_linear_load_combination_recovery_sha256": "sha256:"
            + "7" * 64,
            "workbench_nested_linear_load_combination_report_ir_sha256": "sha256:"
            + "8" * 64,
            "workbench_nested_linear_load_combination_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v47_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v46_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v47",
            "workbench_direct_linear_load_combination_delete_surface_passed": True,
            "workbench_direct_linear_load_combination_delete_model_sha256": "sha256:"
            + "9" * 64,
            "workbench_direct_linear_load_combination_delete_receipt_sha256": "sha256:"
            + "a" * 64,
            "workbench_direct_linear_load_combination_delete_request_sha256": "sha256:"
            + "b" * 64,
            "workbench_direct_linear_load_combination_delete_assembly_receipt_sha256": "sha256:"
            + "c" * 64,
            "workbench_direct_linear_load_combination_delete_checkpoint_sha256": "sha256:"
            + "d" * 64,
            "workbench_direct_linear_load_combination_delete_result_ir_sha256": "sha256:"
            + "e" * 64,
            "workbench_direct_linear_load_combination_delete_recovery_sha256": "sha256:"
            + "f" * 64,
            "workbench_direct_linear_load_combination_delete_report_ir_sha256": "sha256:"
            + "0" * 64,
            "workbench_direct_linear_load_combination_delete_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v48_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v47_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v48",
            "workbench_nested_linear_load_combination_delete_surface_passed": True,
            "workbench_nested_linear_load_combination_delete_model_sha256": "sha256:"
            + "1" * 64,
            "workbench_nested_linear_load_combination_delete_receipt_sha256": "sha256:"
            + "2" * 64,
            "workbench_nested_linear_load_combination_delete_request_receipt_sha256": "sha256:"
            + "3" * 64,
            "workbench_nested_linear_load_combination_delete_request_sha256": "sha256:"
            + "4" * 64,
            "workbench_nested_linear_load_combination_delete_assembly_receipt_sha256": "sha256:"
            + "5" * 64,
            "workbench_nested_linear_load_combination_delete_checkpoint_sha256": "sha256:"
            + "6" * 64,
            "workbench_nested_linear_load_combination_delete_result_ir_sha256": "sha256:"
            + "7" * 64,
            "workbench_nested_linear_load_combination_delete_recovery_sha256": "sha256:"
            + "8" * 64,
            "workbench_nested_linear_load_combination_delete_report_ir_sha256": "sha256:"
            + "9" * 64,
            "workbench_nested_linear_load_combination_delete_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v49_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v48_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v49",
            "workbench_direct_linear_load_combination_factor_edit_surface_passed": True,
            "workbench_direct_linear_load_combination_factor_edit_model_sha256": "sha256:"
            + "a" * 64,
            "workbench_direct_linear_load_combination_factor_edit_receipt_sha256": "sha256:"
            + "b" * 64,
            "workbench_direct_linear_load_combination_factor_edit_request_receipt_sha256": "sha256:"
            + "c" * 64,
            "workbench_direct_linear_load_combination_factor_edit_request_sha256": "sha256:"
            + "d" * 64,
            "workbench_direct_linear_load_combination_factor_edit_assembly_receipt_sha256": "sha256:"
            + "e" * 64,
            "workbench_direct_linear_load_combination_factor_edit_checkpoint_sha256": "sha256:"
            + "f" * 64,
            "workbench_direct_linear_load_combination_factor_edit_result_ir_sha256": "sha256:"
            + "0" * 64,
            "workbench_direct_linear_load_combination_factor_edit_recovery_sha256": "sha256:"
            + "1" * 64,
            "workbench_direct_linear_load_combination_factor_edit_report_ir_sha256": "sha256:"
            + "2" * 64,
            "workbench_direct_linear_load_combination_factor_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v50_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v49_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v50",
            "workbench_nested_linear_load_combination_factor_edit_surface_passed": True,
            "workbench_nested_linear_load_combination_factor_edit_model_sha256": "sha256:"
            + "3" * 64,
            "workbench_nested_linear_load_combination_factor_edit_receipt_sha256": "sha256:"
            + "4" * 64,
            "workbench_nested_linear_load_combination_factor_edit_request_receipt_sha256": "sha256:"
            + "5" * 64,
            "workbench_nested_linear_load_combination_factor_edit_request_sha256": "sha256:"
            + "6" * 64,
            "workbench_nested_linear_load_combination_factor_edit_assembly_receipt_sha256": "sha256:"
            + "7" * 64,
            "workbench_nested_linear_load_combination_factor_edit_checkpoint_sha256": "sha256:"
            + "8" * 64,
            "workbench_nested_linear_load_combination_factor_edit_result_ir_sha256": "sha256:"
            + "9" * 64,
            "workbench_nested_linear_load_combination_factor_edit_recovery_sha256": "sha256:"
            + "a" * 64,
            "workbench_nested_linear_load_combination_factor_edit_report_ir_sha256": "sha256:"
            + "b" * 64,
            "workbench_nested_linear_load_combination_factor_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v51_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v50_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v51",
            "workbench_direct_linear_load_combination_reference_edit_surface_passed": True,
            "workbench_direct_linear_load_combination_reference_edit_model_sha256": "sha256:"
            + "c" * 64,
            "workbench_direct_linear_load_combination_reference_edit_receipt_sha256": "sha256:"
            + "d" * 64,
            "workbench_direct_linear_load_combination_reference_edit_request_receipt_sha256": "sha256:"
            + "e" * 64,
            "workbench_direct_linear_load_combination_reference_edit_request_sha256": "sha256:"
            + "f" * 64,
            "workbench_direct_linear_load_combination_reference_edit_assembly_receipt_sha256": "sha256:"
            + "0" * 64,
            "workbench_direct_linear_load_combination_reference_edit_checkpoint_sha256": "sha256:"
            + "1" * 64,
            "workbench_direct_linear_load_combination_reference_edit_result_ir_sha256": "sha256:"
            + "2" * 64,
            "workbench_direct_linear_load_combination_reference_edit_recovery_sha256": "sha256:"
            + "3" * 64,
            "workbench_direct_linear_load_combination_reference_edit_report_ir_sha256": "sha256:"
            + "4" * 64,
            "workbench_direct_linear_load_combination_reference_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v52_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v51_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v52",
            "workbench_nested_linear_load_combination_reference_edit_surface_passed": True,
            "workbench_nested_linear_load_combination_reference_edit_model_sha256": "sha256:"
            + "5" * 64,
            "workbench_nested_linear_load_combination_reference_edit_receipt_sha256": "sha256:"
            + "6" * 64,
            "workbench_nested_linear_load_combination_reference_edit_request_receipt_sha256": "sha256:"
            + "7" * 64,
            "workbench_nested_linear_load_combination_reference_edit_request_sha256": "sha256:"
            + "8" * 64,
            "workbench_nested_linear_load_combination_reference_edit_assembly_receipt_sha256": "sha256:"
            + "9" * 64,
            "workbench_nested_linear_load_combination_reference_edit_checkpoint_sha256": "sha256:"
            + "a" * 64,
            "workbench_nested_linear_load_combination_reference_edit_result_ir_sha256": "sha256:"
            + "b" * 64,
            "workbench_nested_linear_load_combination_reference_edit_recovery_sha256": "sha256:"
            + "c" * 64,
            "workbench_nested_linear_load_combination_reference_edit_report_ir_sha256": "sha256:"
            + "d" * 64,
            "workbench_nested_linear_load_combination_reference_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v53_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v52_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v53",
            "workbench_direct_linear_load_combination_term_add_surface_passed": True,
            "workbench_direct_linear_load_combination_term_add_model_sha256": "sha256:"
            + "e" * 64,
            "workbench_direct_linear_load_combination_term_add_receipt_sha256": "sha256:"
            + "f" * 64,
            "workbench_direct_linear_load_combination_term_add_request_receipt_sha256": "sha256:"
            + "0" * 64,
            "workbench_direct_linear_load_combination_term_add_request_sha256": "sha256:"
            + "1" * 64,
            "workbench_direct_linear_load_combination_term_add_assembly_receipt_sha256": "sha256:"
            + "2" * 64,
            "workbench_direct_linear_load_combination_term_add_checkpoint_sha256": "sha256:"
            + "3" * 64,
            "workbench_direct_linear_load_combination_term_add_result_ir_sha256": "sha256:"
            + "4" * 64,
            "workbench_direct_linear_load_combination_term_add_recovery_sha256": "sha256:"
            + "5" * 64,
            "workbench_direct_linear_load_combination_term_add_report_ir_sha256": "sha256:"
            + "6" * 64,
            "workbench_direct_linear_load_combination_term_add_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v54_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v53_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v54",
            "workbench_direct_linear_load_combination_term_delete_surface_passed": True,
            "workbench_direct_linear_load_combination_term_delete_model_sha256": "sha256:"
            + "7" * 64,
            "workbench_direct_linear_load_combination_term_delete_receipt_sha256": "sha256:"
            + "8" * 64,
            "workbench_direct_linear_load_combination_term_delete_request_receipt_sha256": "sha256:"
            + "9" * 64,
            "workbench_direct_linear_load_combination_term_delete_request_sha256": "sha256:"
            + "a" * 64,
            "workbench_direct_linear_load_combination_term_delete_assembly_receipt_sha256": "sha256:"
            + "b" * 64,
            "workbench_direct_linear_load_combination_term_delete_checkpoint_sha256": "sha256:"
            + "c" * 64,
            "workbench_direct_linear_load_combination_term_delete_result_ir_sha256": "sha256:"
            + "d" * 64,
            "workbench_direct_linear_load_combination_term_delete_recovery_sha256": "sha256:"
            + "e" * 64,
            "workbench_direct_linear_load_combination_term_delete_report_ir_sha256": "sha256:"
            + "f" * 64,
            "workbench_direct_linear_load_combination_term_delete_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v55_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v54_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v55",
            "workbench_nested_linear_load_combination_term_add_surface_passed": True,
            "workbench_nested_linear_load_combination_term_add_model_sha256": "sha256:"
            + "0" * 64,
            "workbench_nested_linear_load_combination_term_add_receipt_sha256": "sha256:"
            + "1" * 64,
            "workbench_nested_linear_load_combination_term_add_request_receipt_sha256": "sha256:"
            + "2" * 64,
            "workbench_nested_linear_load_combination_term_add_request_sha256": "sha256:"
            + "3" * 64,
            "workbench_nested_linear_load_combination_term_add_assembly_receipt_sha256": "sha256:"
            + "4" * 64,
            "workbench_nested_linear_load_combination_term_add_checkpoint_sha256": "sha256:"
            + "5" * 64,
            "workbench_nested_linear_load_combination_term_add_result_ir_sha256": "sha256:"
            + "6" * 64,
            "workbench_nested_linear_load_combination_term_add_recovery_sha256": "sha256:"
            + "7" * 64,
            "workbench_nested_linear_load_combination_term_add_report_ir_sha256": "sha256:"
            + "8" * 64,
            "workbench_nested_linear_load_combination_term_add_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v56_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v55_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v56",
            "workbench_nested_linear_load_combination_term_delete_surface_passed": True,
            "workbench_nested_linear_load_combination_term_delete_model_sha256": "sha256:"
            + "9" * 64,
            "workbench_nested_linear_load_combination_term_delete_receipt_sha256": "sha256:"
            + "a" * 64,
            "workbench_nested_linear_load_combination_term_delete_request_receipt_sha256": "sha256:"
            + "b" * 64,
            "workbench_nested_linear_load_combination_term_delete_request_sha256": "sha256:"
            + "c" * 64,
            "workbench_nested_linear_load_combination_term_delete_assembly_receipt_sha256": "sha256:"
            + "d" * 64,
            "workbench_nested_linear_load_combination_term_delete_checkpoint_sha256": "sha256:"
            + "e" * 64,
            "workbench_nested_linear_load_combination_term_delete_result_ir_sha256": "sha256:"
            + "f" * 64,
            "workbench_nested_linear_load_combination_term_delete_recovery_sha256": "sha256:"
            + "0" * 64,
            "workbench_nested_linear_load_combination_term_delete_report_ir_sha256": "sha256:"
            + "1" * 64,
            "workbench_nested_linear_load_combination_term_delete_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v57_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v56_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v57",
            "workbench_nested_linear_load_combination_term_reorder_surface_passed": True,
            "workbench_nested_linear_load_combination_term_reorder_model_sha256": "sha256:"
            + "2" * 64,
            "workbench_nested_linear_load_combination_term_reorder_receipt_sha256": "sha256:"
            + "3" * 64,
            "workbench_nested_linear_load_combination_term_reorder_request_receipt_sha256": "sha256:"
            + "4" * 64,
            "workbench_nested_linear_load_combination_term_reorder_request_sha256": "sha256:"
            + "5" * 64,
            "workbench_nested_linear_load_combination_term_reorder_assembly_receipt_sha256": "sha256:"
            + "6" * 64,
            "workbench_nested_linear_load_combination_term_reorder_checkpoint_sha256": "sha256:"
            + "7" * 64,
            "workbench_nested_linear_load_combination_term_reorder_result_ir_sha256": "sha256:"
            + "8" * 64,
            "workbench_nested_linear_load_combination_term_reorder_recovery_sha256": "sha256:"
            + "9" * 64,
            "workbench_nested_linear_load_combination_term_reorder_report_ir_sha256": "sha256:"
            + "a" * 64,
            "workbench_nested_linear_load_combination_term_reorder_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v58_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v57_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v58",
            "workbench_direct_linear_load_combination_term_reorder_surface_passed": True,
            "workbench_direct_linear_load_combination_term_reorder_model_sha256": "sha256:"
            + "b" * 64,
            "workbench_direct_linear_load_combination_term_reorder_receipt_sha256": "sha256:"
            + "c" * 64,
            "workbench_direct_linear_load_combination_term_reorder_request_receipt_sha256": "sha256:"
            + "d" * 64,
            "workbench_direct_linear_load_combination_term_reorder_request_sha256": "sha256:"
            + "e" * 64,
            "workbench_direct_linear_load_combination_term_reorder_assembly_receipt_sha256": "sha256:"
            + "f" * 64,
            "workbench_direct_linear_load_combination_term_reorder_checkpoint_sha256": "sha256:"
            + "0" * 64,
            "workbench_direct_linear_load_combination_term_reorder_result_ir_sha256": "sha256:"
            + "1" * 64,
            "workbench_direct_linear_load_combination_term_reorder_recovery_sha256": "sha256:"
            + "2" * 64,
            "workbench_direct_linear_load_combination_term_reorder_report_ir_sha256": "sha256:"
            + "3" * 64,
            "workbench_direct_linear_load_combination_term_reorder_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v59_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v58_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v59",
            "workbench_direct_linear_load_combination_term_insert_surface_passed": True,
            "workbench_direct_linear_load_combination_term_insert_model_sha256": "sha256:"
            + "4" * 64,
            "workbench_direct_linear_load_combination_term_insert_receipt_sha256": "sha256:"
            + "5" * 64,
            "workbench_direct_linear_load_combination_term_insert_request_receipt_sha256": "sha256:"
            + "6" * 64,
            "workbench_direct_linear_load_combination_term_insert_request_sha256": "sha256:"
            + "7" * 64,
            "workbench_direct_linear_load_combination_term_insert_assembly_receipt_sha256": "sha256:"
            + "8" * 64,
            "workbench_direct_linear_load_combination_term_insert_checkpoint_sha256": "sha256:"
            + "9" * 64,
            "workbench_direct_linear_load_combination_term_insert_result_ir_sha256": "sha256:"
            + "a" * 64,
            "workbench_direct_linear_load_combination_term_insert_recovery_sha256": "sha256:"
            + "b" * 64,
            "workbench_direct_linear_load_combination_term_insert_report_ir_sha256": "sha256:"
            + "c" * 64,
            "workbench_direct_linear_load_combination_term_insert_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v60_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v59_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v60",
            "workbench_nested_linear_load_combination_term_insert_surface_passed": True,
            "workbench_nested_linear_load_combination_term_insert_model_sha256": "sha256:"
            + "d" * 64,
            "workbench_nested_linear_load_combination_term_insert_receipt_sha256": "sha256:"
            + "e" * 64,
            "workbench_nested_linear_load_combination_term_insert_request_receipt_sha256": "sha256:"
            + "f" * 64,
            "workbench_nested_linear_load_combination_term_insert_request_sha256": "sha256:"
            + "0" * 64,
            "workbench_nested_linear_load_combination_term_insert_assembly_receipt_sha256": "sha256:"
            + "1" * 64,
            "workbench_nested_linear_load_combination_term_insert_checkpoint_sha256": "sha256:"
            + "2" * 64,
            "workbench_nested_linear_load_combination_term_insert_result_ir_sha256": "sha256:"
            + "3" * 64,
            "workbench_nested_linear_load_combination_term_insert_recovery_sha256": "sha256:"
            + "4" * 64,
            "workbench_nested_linear_load_combination_term_insert_report_ir_sha256": "sha256:"
            + "5" * 64,
            "workbench_nested_linear_load_combination_term_insert_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v61_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v60_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v61",
            "workbench_nodal_load_target_edit_surface_passed": True,
            "workbench_nodal_load_target_edit_model_sha256": "sha256:" + "6" * 64,
            "workbench_nodal_load_target_edit_receipt_sha256": "sha256:" + "7" * 64,
            "workbench_nodal_load_target_edit_request_receipt_sha256": "sha256:"
            + "8" * 64,
            "workbench_nodal_load_target_edit_request_sha256": "sha256:" + "9" * 64,
            "workbench_nodal_load_target_edit_assembly_receipt_sha256": "sha256:"
            + "a" * 64,
            "workbench_nodal_load_target_edit_checkpoint_sha256": "sha256:" + "b" * 64,
            "workbench_nodal_load_target_edit_result_ir_sha256": "sha256:" + "c" * 64,
            "workbench_nodal_load_target_edit_recovery_sha256": "sha256:" + "d" * 64,
            "workbench_nodal_load_target_edit_report_ir_sha256": "sha256:" + "e" * 64,
            "workbench_nodal_load_target_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v62_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v61_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v62",
            "workbench_constraint_target_edit_surface_passed": True,
            "workbench_constraint_target_edit_model_sha256": "sha256:" + "f" * 64,
            "workbench_constraint_target_edit_receipt_sha256": "sha256:" + "0" * 64,
            "workbench_constraint_target_edit_request_receipt_sha256": "sha256:"
            + "1" * 64,
            "workbench_constraint_target_edit_request_sha256": "sha256:" + "2" * 64,
            "workbench_constraint_target_edit_assembly_receipt_sha256": "sha256:"
            + "3" * 64,
            "workbench_constraint_target_edit_checkpoint_sha256": "sha256:" + "4" * 64,
            "workbench_constraint_target_edit_result_ir_sha256": "sha256:" + "5" * 64,
            "workbench_constraint_target_edit_recovery_sha256": "sha256:" + "6" * 64,
            "workbench_constraint_target_edit_report_ir_sha256": "sha256:" + "7" * 64,
            "workbench_constraint_target_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v63_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v62_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v63",
            "workbench_fixed_constraint_dof_delete_surface_passed": True,
            "workbench_fixed_constraint_dof_delete_model_sha256": "sha256:" + "8" * 64,
            "workbench_fixed_constraint_dof_delete_receipt_sha256": "sha256:"
            + "9" * 64,
            "workbench_fixed_constraint_dof_delete_request_receipt_sha256": "sha256:"
            + "a" * 64,
            "workbench_fixed_constraint_dof_delete_request_sha256": "sha256:"
            + "b" * 64,
            "workbench_fixed_constraint_dof_delete_assembly_receipt_sha256": "sha256:"
            + "c" * 64,
            "workbench_fixed_constraint_dof_delete_checkpoint_sha256": "sha256:"
            + "d" * 64,
            "workbench_fixed_constraint_dof_delete_result_ir_sha256": "sha256:"
            + "e" * 64,
            "workbench_fixed_constraint_dof_delete_recovery_sha256": "sha256:"
            + "f" * 64,
            "workbench_fixed_constraint_dof_delete_report_ir_sha256": "sha256:"
            + "0" * 64,
            "workbench_fixed_constraint_dof_delete_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v64_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v63_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v64",
            "workbench_fixed_constraint_dof_add_surface_passed": True,
            "workbench_fixed_constraint_dof_add_model_sha256": "sha256:" + "1" * 64,
            "workbench_fixed_constraint_dof_add_receipt_sha256": "sha256:" + "2" * 64,
            "workbench_fixed_constraint_dof_add_request_receipt_sha256": "sha256:"
            + "3" * 64,
            "workbench_fixed_constraint_dof_add_request_sha256": "sha256:" + "4" * 64,
            "workbench_fixed_constraint_dof_add_assembly_receipt_sha256": "sha256:"
            + "5" * 64,
            "workbench_fixed_constraint_dof_add_checkpoint_sha256": "sha256:"
            + "6" * 64,
            "workbench_fixed_constraint_dof_add_result_ir_sha256": "sha256:" + "7" * 64,
            "workbench_fixed_constraint_dof_add_recovery_sha256": "sha256:" + "8" * 64,
            "workbench_fixed_constraint_dof_add_report_ir_sha256": "sha256:" + "9" * 64,
            "workbench_fixed_constraint_dof_add_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v65_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v64_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v65",
            "workbench_fixed_constraint_dof_reorder_surface_passed": True,
            "workbench_fixed_constraint_dof_reorder_model_sha256": "sha256:" + "a" * 64,
            "workbench_fixed_constraint_dof_reorder_receipt_sha256": "sha256:"
            + "b" * 64,
            "workbench_fixed_constraint_dof_reorder_request_receipt_sha256": "sha256:"
            + "c" * 64,
            "workbench_fixed_constraint_dof_reorder_request_sha256": "sha256:"
            + "d" * 64,
            "workbench_fixed_constraint_dof_reorder_assembly_receipt_sha256": "sha256:"
            + "e" * 64,
            "workbench_fixed_constraint_dof_reorder_checkpoint_sha256": "sha256:"
            + "f" * 64,
            "workbench_fixed_constraint_dof_reorder_result_ir_sha256": "sha256:"
            + "0" * 64,
            "workbench_fixed_constraint_dof_reorder_recovery_sha256": "sha256:"
            + "1" * 64,
            "workbench_fixed_constraint_dof_reorder_report_ir_sha256": "sha256:"
            + "2" * 64,
            "workbench_fixed_constraint_dof_reorder_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v66_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v65_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v66",
            "workbench_fixed_constraint_identity_edit_surface_passed": True,
            "workbench_fixed_constraint_identity_edit_model_sha256": "sha256:"
            + "3" * 64,
            "workbench_fixed_constraint_identity_edit_receipt_sha256": "sha256:"
            + "4" * 64,
            "workbench_fixed_constraint_identity_edit_request_receipt_sha256": "sha256:"
            + "5" * 64,
            "workbench_fixed_constraint_identity_edit_request_sha256": "sha256:"
            + "6" * 64,
            "workbench_fixed_constraint_identity_edit_assembly_receipt_sha256": "sha256:"
            + "7" * 64,
            "workbench_fixed_constraint_identity_edit_checkpoint_sha256": "sha256:"
            + "8" * 64,
            "workbench_fixed_constraint_identity_edit_result_ir_sha256": "sha256:"
            + "9" * 64,
            "workbench_fixed_constraint_identity_edit_recovery_sha256": "sha256:"
            + "a" * 64,
            "workbench_fixed_constraint_identity_edit_report_ir_sha256": "sha256:"
            + "b" * 64,
            "workbench_fixed_constraint_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v67_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v66_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v67",
            "workbench_nodal_load_identity_edit_surface_passed": True,
            "workbench_nodal_load_identity_edit_model_sha256": "sha256:" + "c" * 64,
            "workbench_nodal_load_identity_edit_receipt_sha256": "sha256:" + "d" * 64,
            "workbench_nodal_load_identity_edit_request_receipt_sha256": "sha256:"
            + "e" * 64,
            "workbench_nodal_load_identity_edit_request_sha256": "sha256:" + "f" * 64,
            "workbench_nodal_load_identity_edit_assembly_receipt_sha256": "sha256:"
            + "0" * 64,
            "workbench_nodal_load_identity_edit_checkpoint_sha256": "sha256:"
            + "1" * 64,
            "workbench_nodal_load_identity_edit_result_ir_sha256": "sha256:" + "2" * 64,
            "workbench_nodal_load_identity_edit_recovery_sha256": "sha256:" + "3" * 64,
            "workbench_nodal_load_identity_edit_report_ir_sha256": "sha256:" + "4" * 64,
            "workbench_nodal_load_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v68_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v67_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v68",
            "workbench_linear_load_pattern_identity_edit_surface_passed": True,
            "workbench_linear_load_pattern_identity_edit_model_sha256": "sha256:"
            + "5" * 64,
            "workbench_linear_load_pattern_identity_edit_receipt_sha256": "sha256:"
            + "6" * 64,
            "workbench_linear_load_pattern_identity_edit_request_receipt_sha256": "sha256:"
            + "7" * 64,
            "workbench_linear_load_pattern_identity_edit_request_sha256": "sha256:"
            + "8" * 64,
            "workbench_linear_load_pattern_identity_edit_assembly_receipt_sha256": "sha256:"
            + "9" * 64,
            "workbench_linear_load_pattern_identity_edit_checkpoint_sha256": "sha256:"
            + "a" * 64,
            "workbench_linear_load_pattern_identity_edit_result_ir_sha256": "sha256:"
            + "b" * 64,
            "workbench_linear_load_pattern_identity_edit_recovery_sha256": "sha256:"
            + "c" * 64,
            "workbench_linear_load_pattern_identity_edit_report_ir_sha256": "sha256:"
            + "d" * 64,
            "workbench_linear_load_pattern_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v69_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v68_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v69",
            "workbench_linear_material_identity_edit_surface_passed": True,
            "workbench_linear_material_identity_edit_model_sha256": "sha256:"
            + "e" * 64,
            "workbench_linear_material_identity_edit_receipt_sha256": "sha256:"
            + "f" * 64,
            "workbench_linear_material_identity_edit_request_receipt_sha256": "sha256:"
            + "0" * 64,
            "workbench_linear_material_identity_edit_request_sha256": "sha256:"
            + "1" * 64,
            "workbench_linear_material_identity_edit_assembly_receipt_sha256": "sha256:"
            + "2" * 64,
            "workbench_linear_material_identity_edit_checkpoint_sha256": "sha256:"
            + "3" * 64,
            "workbench_linear_material_identity_edit_result_ir_sha256": "sha256:"
            + "4" * 64,
            "workbench_linear_material_identity_edit_recovery_sha256": "sha256:"
            + "5" * 64,
            "workbench_linear_material_identity_edit_report_ir_sha256": "sha256:"
            + "6" * 64,
            "workbench_linear_material_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v70_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v69_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v70",
            "workbench_frame_section_identity_edit_surface_passed": True,
            "workbench_frame_section_identity_edit_model_sha256": "sha256:" + "7" * 64,
            "workbench_frame_section_identity_edit_receipt_sha256": "sha256:"
            + "8" * 64,
            "workbench_frame_section_identity_edit_request_receipt_sha256": "sha256:"
            + "9" * 64,
            "workbench_frame_section_identity_edit_request_sha256": "sha256:"
            + "a" * 64,
            "workbench_frame_section_identity_edit_assembly_receipt_sha256": "sha256:"
            + "b" * 64,
            "workbench_frame_section_identity_edit_checkpoint_sha256": "sha256:"
            + "c" * 64,
            "workbench_frame_section_identity_edit_result_ir_sha256": "sha256:"
            + "d" * 64,
            "workbench_frame_section_identity_edit_recovery_sha256": "sha256:"
            + "e" * 64,
            "workbench_frame_section_identity_edit_report_ir_sha256": "sha256:"
            + "f" * 64,
            "workbench_frame_section_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v71_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v70_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v71",
            "workbench_truss_section_identity_edit_surface_passed": True,
            "workbench_truss_section_identity_edit_model_sha256": "sha256:" + "0" * 64,
            "workbench_truss_section_identity_edit_receipt_sha256": "sha256:"
            + "1" * 64,
            "workbench_truss_section_identity_edit_request_receipt_sha256": "sha256:"
            + "2" * 64,
            "workbench_truss_section_identity_edit_request_sha256": "sha256:"
            + "3" * 64,
            "workbench_truss_section_identity_edit_assembly_receipt_sha256": "sha256:"
            + "4" * 64,
            "workbench_truss_section_identity_edit_checkpoint_sha256": "sha256:"
            + "5" * 64,
            "workbench_truss_section_identity_edit_result_ir_sha256": "sha256:"
            + "6" * 64,
            "workbench_truss_section_identity_edit_recovery_sha256": "sha256:"
            + "7" * 64,
            "workbench_truss_section_identity_edit_report_ir_sha256": "sha256:"
            + "8" * 64,
            "workbench_truss_section_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v72_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v71_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v72",
            "workbench_node_identity_edit_surface_passed": True,
            "workbench_node_identity_edit_model_sha256": "sha256:" + "9" * 64,
            "workbench_node_identity_edit_receipt_sha256": "sha256:" + "a" * 64,
            "workbench_node_identity_edit_request_receipt_sha256": "sha256:" + "b" * 64,
            "workbench_node_identity_edit_request_sha256": "sha256:" + "c" * 64,
            "workbench_node_identity_edit_assembly_receipt_sha256": "sha256:"
            + "d" * 64,
            "workbench_node_identity_edit_checkpoint_sha256": "sha256:" + "e" * 64,
            "workbench_node_identity_edit_result_ir_sha256": "sha256:" + "f" * 64,
            "workbench_node_identity_edit_recovery_sha256": "sha256:" + "0" * 64,
            "workbench_node_identity_edit_report_ir_sha256": "sha256:" + "1" * 64,
            "workbench_node_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v73_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v72_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v73",
            "workbench_element_identity_edit_surface_passed": True,
            "workbench_element_identity_edit_model_sha256": "sha256:" + "2" * 64,
            "workbench_element_identity_edit_receipt_sha256": "sha256:" + "3" * 64,
            "workbench_element_identity_edit_request_receipt_sha256": "sha256:"
            + "4" * 64,
            "workbench_element_identity_edit_request_sha256": "sha256:" + "5" * 64,
            "workbench_element_identity_edit_assembly_receipt_sha256": "sha256:"
            + "6" * 64,
            "workbench_element_identity_edit_checkpoint_sha256": "sha256:" + "7" * 64,
            "workbench_element_identity_edit_result_ir_sha256": "sha256:" + "8" * 64,
            "workbench_element_identity_edit_recovery_sha256": "sha256:" + "9" * 64,
            "workbench_element_identity_edit_report_ir_sha256": "sha256:" + "a" * 64,
            "workbench_element_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v74_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v73_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v74",
            "workbench_linear_load_combination_identity_edit_surface_passed": True,
            "workbench_linear_load_combination_identity_edit_model_sha256": "sha256:"
            + "b" * 64,
            "workbench_linear_load_combination_identity_edit_receipt_sha256": "sha256:"
            + "c" * 64,
            "workbench_linear_load_combination_identity_edit_request_receipt_sha256": "sha256:"
            + "d" * 64,
            "workbench_linear_load_combination_identity_edit_request_sha256": "sha256:"
            + "e" * 64,
            "workbench_linear_load_combination_identity_edit_assembly_receipt_sha256": "sha256:"
            + "f" * 64,
            "workbench_linear_load_combination_identity_edit_checkpoint_sha256": "sha256:"
            + "0" * 64,
            "workbench_linear_load_combination_identity_edit_result_ir_sha256": "sha256:"
            + "1" * 64,
            "workbench_linear_load_combination_identity_edit_recovery_sha256": "sha256:"
            + "2" * 64,
            "workbench_linear_load_combination_identity_edit_report_ir_sha256": "sha256:"
            + "3" * 64,
            "workbench_linear_load_combination_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v75_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v74_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v75",
            "workbench_model_identity_edit_surface_passed": True,
            "workbench_model_identity_edit_model_sha256": "sha256:" + "4" * 64,
            "workbench_model_identity_edit_receipt_sha256": "sha256:" + "5" * 64,
            "workbench_model_identity_edit_request_receipt_sha256": "sha256:"
            + "6" * 64,
            "workbench_model_identity_edit_request_sha256": "sha256:" + "7" * 64,
            "workbench_model_identity_edit_assembly_receipt_sha256": "sha256:"
            + "8" * 64,
            "workbench_model_identity_edit_checkpoint_sha256": "sha256:" + "9" * 64,
            "workbench_model_identity_edit_result_ir_sha256": "sha256:" + "a" * 64,
            "workbench_model_identity_edit_recovery_sha256": "sha256:" + "b" * 64,
            "workbench_model_identity_edit_report_ir_sha256": "sha256:" + "c" * 64,
            "workbench_model_identity_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v76_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v75_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v76",
            "workbench_node_identity_cascade_edit_surface_passed": True,
            "workbench_node_identity_cascade_edit_model_sha256": "sha256:" + "d" * 64,
            "workbench_node_identity_cascade_edit_receipt_sha256": "sha256:" + "e" * 64,
            "workbench_node_identity_cascade_edit_request_receipt_sha256": "sha256:"
            + "f" * 64,
            "workbench_node_identity_cascade_edit_request_sha256": "sha256:" + "0" * 64,
            "workbench_node_identity_cascade_edit_assembly_receipt_sha256": "sha256:"
            + "1" * 64,
            "workbench_node_identity_cascade_edit_checkpoint_sha256": "sha256:"
            + "2" * 64,
            "workbench_node_identity_cascade_edit_result_ir_sha256": "sha256:"
            + "3" * 64,
            "workbench_node_identity_cascade_edit_recovery_sha256": "sha256:"
            + "4" * 64,
            "workbench_node_identity_cascade_edit_report_ir_sha256": "sha256:"
            + "5" * 64,
            "workbench_node_identity_cascade_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v77_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v76_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v77",
            "workbench_frame_section_identity_cascade_edit_surface_passed": True,
            "workbench_frame_section_identity_cascade_edit_model_sha256": "sha256:"
            + "6" * 64,
            "workbench_frame_section_identity_cascade_edit_receipt_sha256": "sha256:"
            + "7" * 64,
            "workbench_frame_section_identity_cascade_edit_request_receipt_sha256": "sha256:"
            + "8" * 64,
            "workbench_frame_section_identity_cascade_edit_request_sha256": "sha256:"
            + "9" * 64,
            "workbench_frame_section_identity_cascade_edit_assembly_receipt_sha256": "sha256:"
            + "a" * 64,
            "workbench_frame_section_identity_cascade_edit_checkpoint_sha256": "sha256:"
            + "b" * 64,
            "workbench_frame_section_identity_cascade_edit_result_ir_sha256": "sha256:"
            + "c" * 64,
            "workbench_frame_section_identity_cascade_edit_recovery_sha256": "sha256:"
            + "d" * 64,
            "workbench_frame_section_identity_cascade_edit_report_ir_sha256": "sha256:"
            + "e" * 64,
            "workbench_frame_section_identity_cascade_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v78_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v77_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v78",
            "workbench_linear_material_identity_cascade_edit_surface_passed": True,
            "workbench_linear_material_identity_cascade_edit_model_sha256": "sha256:"
            + "f" * 64,
            "workbench_linear_material_identity_cascade_edit_receipt_sha256": "sha256:"
            + "0" * 64,
            "workbench_linear_material_identity_cascade_edit_request_receipt_sha256": "sha256:"
            + "1" * 64,
            "workbench_linear_material_identity_cascade_edit_request_sha256": "sha256:"
            + "2" * 64,
            "workbench_linear_material_identity_cascade_edit_assembly_receipt_sha256": "sha256:"
            + "3" * 64,
            "workbench_linear_material_identity_cascade_edit_checkpoint_sha256": "sha256:"
            + "4" * 64,
            "workbench_linear_material_identity_cascade_edit_result_ir_sha256": "sha256:"
            + "5" * 64,
            "workbench_linear_material_identity_cascade_edit_recovery_sha256": "sha256:"
            + "6" * 64,
            "workbench_linear_material_identity_cascade_edit_report_ir_sha256": "sha256:"
            + "7" * 64,
            "workbench_linear_material_identity_cascade_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v79_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v78_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v79",
            "workbench_truss_section_identity_cascade_edit_surface_passed": True,
            "workbench_truss_section_identity_cascade_edit_model_sha256": "sha256:"
            + "8" * 64,
            "workbench_truss_section_identity_cascade_edit_receipt_sha256": "sha256:"
            + "9" * 64,
            "workbench_truss_section_identity_cascade_edit_request_receipt_sha256": "sha256:"
            + "a" * 64,
            "workbench_truss_section_identity_cascade_edit_request_sha256": "sha256:"
            + "b" * 64,
            "workbench_truss_section_identity_cascade_edit_assembly_receipt_sha256": "sha256:"
            + "c" * 64,
            "workbench_truss_section_identity_cascade_edit_checkpoint_sha256": "sha256:"
            + "d" * 64,
            "workbench_truss_section_identity_cascade_edit_result_ir_sha256": "sha256:"
            + "e" * 64,
            "workbench_truss_section_identity_cascade_edit_recovery_sha256": "sha256:"
            + "f" * 64,
            "workbench_truss_section_identity_cascade_edit_report_ir_sha256": "sha256:"
            + "0" * 64,
            "workbench_truss_section_identity_cascade_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v80_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v79_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v80",
            "workbench_linear_load_pattern_identity_cascade_edit_surface_passed": True,
            "workbench_linear_load_pattern_identity_cascade_edit_model_sha256": "sha256:"
            + "1" * 64,
            "workbench_linear_load_pattern_identity_cascade_edit_receipt_sha256": "sha256:"
            + "2" * 64,
            "workbench_linear_load_pattern_identity_cascade_edit_request_receipt_sha256": "sha256:"
            + "3" * 64,
            "workbench_linear_load_pattern_identity_cascade_edit_request_sha256": "sha256:"
            + "4" * 64,
            "workbench_linear_load_pattern_identity_cascade_edit_assembly_receipt_sha256": "sha256:"
            + "5" * 64,
            "workbench_linear_load_pattern_identity_cascade_edit_checkpoint_sha256": "sha256:"
            + "6" * 64,
            "workbench_linear_load_pattern_identity_cascade_edit_result_ir_sha256": "sha256:"
            + "7" * 64,
            "workbench_linear_load_pattern_identity_cascade_edit_recovery_sha256": "sha256:"
            + "8" * 64,
            "workbench_linear_load_pattern_identity_cascade_edit_report_ir_sha256": "sha256:"
            + "9" * 64,
            "workbench_linear_load_pattern_identity_cascade_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v81_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v80_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v81",
            "workbench_linear_load_combination_identity_cascade_edit_surface_passed": True,
            "workbench_linear_load_combination_identity_cascade_edit_model_sha256": "sha256:"
            + "a" * 64,
            "workbench_linear_load_combination_identity_cascade_edit_receipt_sha256": "sha256:"
            + "b" * 64,
            "workbench_linear_load_combination_identity_cascade_edit_request_receipt_sha256": "sha256:"
            + "c" * 64,
            "workbench_linear_load_combination_identity_cascade_edit_request_sha256": "sha256:"
            + "d" * 64,
            "workbench_linear_load_combination_identity_cascade_edit_assembly_receipt_sha256": "sha256:"
            + "e" * 64,
            "workbench_linear_load_combination_identity_cascade_edit_checkpoint_sha256": "sha256:"
            + "f" * 64,
            "workbench_linear_load_combination_identity_cascade_edit_result_ir_sha256": "sha256:"
            + "0" * 64,
            "workbench_linear_load_combination_identity_cascade_edit_recovery_sha256": "sha256:"
            + "1" * 64,
            "workbench_linear_load_combination_identity_cascade_edit_report_ir_sha256": "sha256:"
            + "2" * 64,
            "workbench_linear_load_combination_identity_cascade_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v82_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v81_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v82",
            "workbench_element_identity_cascade_edit_surface_passed": True,
            "workbench_element_identity_cascade_edit_model_sha256": "sha256:"
            + "3" * 64,
            "workbench_element_identity_cascade_edit_receipt_sha256": "sha256:"
            + "4" * 64,
            "workbench_element_identity_cascade_edit_request_receipt_sha256": "sha256:"
            + "5" * 64,
            "workbench_element_identity_cascade_edit_request_sha256": "sha256:"
            + "6" * 64,
            "workbench_element_identity_cascade_edit_assembly_receipt_sha256": "sha256:"
            + "7" * 64,
            "workbench_element_identity_cascade_edit_checkpoint_sha256": "sha256:"
            + "8" * 64,
            "workbench_element_identity_cascade_edit_result_ir_sha256": "sha256:"
            + "9" * 64,
            "workbench_element_identity_cascade_edit_recovery_sha256": "sha256:"
            + "a" * 64,
            "workbench_element_identity_cascade_edit_report_ir_sha256": "sha256:"
            + "b" * 64,
            "workbench_element_identity_cascade_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v83_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v82_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v83",
            "workbench_fixed_constraint_identity_cascade_edit_surface_passed": True,
            "workbench_fixed_constraint_identity_cascade_edit_model_sha256": "sha256:"
            + "c" * 64,
            "workbench_fixed_constraint_identity_cascade_edit_receipt_sha256": "sha256:"
            + "d" * 64,
            "workbench_fixed_constraint_identity_cascade_edit_request_receipt_sha256": "sha256:"
            + "e" * 64,
            "workbench_fixed_constraint_identity_cascade_edit_request_sha256": "sha256:"
            + "f" * 64,
            "workbench_fixed_constraint_identity_cascade_edit_assembly_receipt_sha256": "sha256:"
            + "0" * 64,
            "workbench_fixed_constraint_identity_cascade_edit_checkpoint_sha256": "sha256:"
            + "1" * 64,
            "workbench_fixed_constraint_identity_cascade_edit_result_ir_sha256": "sha256:"
            + "2" * 64,
            "workbench_fixed_constraint_identity_cascade_edit_recovery_sha256": "sha256:"
            + "3" * 64,
            "workbench_fixed_constraint_identity_cascade_edit_report_ir_sha256": "sha256:"
            + "4" * 64,
            "workbench_fixed_constraint_identity_cascade_edit_restart_passed": True,
        }
    )
    return receipt, manifest


def valid_v84_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v83_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v84",
            "model_ir_linear_reaction_result_ir_sha256": "sha256:" + "5" * 64,
            "mgt_model_ir_linear_reaction_result_ir_sha256": "sha256:" + "6" * 64,
        }
    )
    return receipt, manifest


def valid_v85_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v84_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v85",
            "model_ir_linear_reaction_view_surface_passed": True,
            "model_ir_linear_reaction_view_restart_parity_passed": True,
            "model_ir_linear_reaction_view_en_us_sha256": "sha256:" + "7" * 64,
            "model_ir_linear_reaction_view_ko_kr_sha256": "sha256:" + "8" * 64,
            "model_ir_linear_reaction_view_window_sha256": "sha256:" + "9" * 64,
            "mgt_model_ir_linear_reaction_view_surface_passed": True,
            "mgt_model_ir_linear_reaction_view_restart_parity_passed": True,
            "mgt_model_ir_linear_reaction_view_en_us_sha256": "sha256:" + "a" * 64,
            "mgt_model_ir_linear_reaction_view_ko_kr_sha256": "sha256:" + "b" * 64,
            "workbench_reaction_view_wrong_profile_rejected": True,
        }
    )
    return receipt, manifest


def valid_v86_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v85_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v86",
            "model_ir_linear_reaction_audit_surface_passed": True,
            "model_ir_linear_reaction_audit_restart_parity_passed": True,
            "model_ir_linear_reaction_audit_en_us_sha256": "sha256:" + "c" * 64,
            "model_ir_linear_reaction_audit_ko_kr_sha256": "sha256:" + "d" * 64,
            "mgt_model_ir_linear_reaction_audit_surface_passed": True,
            "mgt_model_ir_linear_reaction_audit_restart_parity_passed": True,
            "mgt_model_ir_linear_reaction_audit_en_us_sha256": "sha256:" + "e" * 64,
            "mgt_model_ir_linear_reaction_audit_ko_kr_sha256": "sha256:" + "f" * 64,
            "workbench_reaction_audit_wrong_profile_rejected": True,
        }
    )
    return receipt, manifest


def valid_v87_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v86_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v87",
            "model_ir_linear_nodal_displacement_view_surface_passed": True,
            "model_ir_linear_nodal_displacement_view_restart_parity_passed": True,
            "model_ir_linear_nodal_displacement_view_en_us_sha256": "sha256:"
            + "0" * 63
            + "1",
            "model_ir_linear_nodal_displacement_view_ko_kr_sha256": "sha256:"
            + "0" * 63
            + "2",
            "model_ir_linear_nodal_displacement_view_window_sha256": "sha256:"
            + "0" * 63
            + "3",
            "mgt_model_ir_linear_nodal_displacement_view_surface_passed": True,
            "mgt_model_ir_linear_nodal_displacement_view_restart_parity_passed": True,
            "mgt_model_ir_linear_nodal_displacement_view_en_us_sha256": "sha256:"
            + "0" * 63
            + "4",
            "mgt_model_ir_linear_nodal_displacement_view_ko_kr_sha256": "sha256:"
            + "0" * 63
            + "5",
            "workbench_nodal_displacement_view_wrong_profile_rejected": True,
        }
    )
    return receipt, manifest


def valid_v88_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v87_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v88",
            "model_ir_linear_deformed_view_surface_passed": True,
            "model_ir_linear_deformed_view_restart_parity_passed": True,
            "model_ir_linear_deformed_view_en_us_sha256": "sha256:" + "1" * 63 + "1",
            "model_ir_linear_deformed_view_ko_kr_sha256": "sha256:" + "1" * 63 + "2",
            "model_ir_linear_deformed_view_projection_sha256": "sha256:"
            + "1" * 63
            + "3",
            "mgt_model_ir_linear_deformed_view_surface_passed": True,
            "mgt_model_ir_linear_deformed_view_restart_parity_passed": True,
            "mgt_model_ir_linear_deformed_view_en_us_sha256": "sha256:"
            + "1" * 63
            + "4",
            "mgt_model_ir_linear_deformed_view_ko_kr_sha256": "sha256:"
            + "1" * 63
            + "5",
            "workbench_linear_deformed_view_invalid_step_rejected": True,
        }
    )
    return receipt, manifest


def valid_v89_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v88_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v89",
            "model_ir_linear_element_recovery_view_surface_passed": True,
            "model_ir_linear_element_recovery_view_restart_parity_passed": True,
            "model_ir_linear_element_recovery_view_en_us_sha256": "sha256:"
            + "2" * 63
            + "1",
            "model_ir_linear_element_recovery_view_ko_kr_sha256": "sha256:"
            + "2" * 63
            + "2",
            "mgt_model_ir_linear_element_recovery_view_surface_passed": True,
            "mgt_model_ir_linear_element_recovery_view_restart_parity_passed": True,
            "mgt_model_ir_linear_element_recovery_view_en_us_sha256": "sha256:"
            + "2" * 63
            + "3",
            "mgt_model_ir_linear_element_recovery_view_ko_kr_sha256": "sha256:"
            + "2" * 63
            + "4",
            "workbench_linear_element_recovery_view_invalid_window_rejected": True,
        }
    )
    return receipt, manifest


def valid_v90_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v89_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v90",
            "workbench_model_modal_request_create_surface_passed": True,
            "model_ir_modal_product_surface_passed": True,
            "model_ir_modal_repeat_bitwise_passed": True,
            "workbench_model_modal_unsupported_planar_rejected": True,
            "model_ir_modal_mode_count": 3,
            "model_ir_modal_active_dof_count": 6,
            "model_ir_modal_fallback_count": 0,
            "model_ir_modal_request_sha256": "sha256:" + "3" * 63 + "1",
            "workbench_model_modal_request_receipt_sha256": "sha256:" + "3" * 63 + "2",
            "model_ir_modal_result_ir_sha256": "sha256:" + "3" * 63 + "3",
            "model_ir_modal_report_ir_sha256": "sha256:" + "3" * 63 + "4",
            "model_ir_modal_markdown_sha256": "sha256:" + "3" * 63 + "5",
            "model_ir_modal_run_receipt_sha256": "sha256:" + "3" * 63 + "6",
        }
    )
    return receipt, manifest


def valid_v91_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v90_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v91",
            "model_ir_modal_restart_surface_passed": True,
            "model_ir_modal_restart_bitwise_passed": True,
            "workbench_model_modal_result_view_surface_passed": True,
            "workbench_model_modal_result_view_read_only_passed": True,
            "workbench_model_modal_result_view_invalid_window_rejected": True,
            "model_ir_modal_checkpoint_sha256": "sha256:" + "4" * 63 + "1",
            "workbench_model_modal_result_view_en_us_sha256": "sha256:"
            + "4" * 63
            + "2",
            "workbench_model_modal_result_view_ko_kr_sha256": "sha256:"
            + "4" * 63
            + "3",
        }
    )
    return receipt, manifest


def valid_v92_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v91_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v92",
            "workbench_model_modal_durable_session_surface_passed": True,
            "workbench_model_modal_durable_session_crash_reconciliation_passed": True,
            "workbench_model_modal_durable_session_restart_bitwise_passed": True,
            "workbench_model_modal_durable_session_tamper_rejected": True,
            "workbench_model_modal_durable_session_null_authority_passed": True,
            "workbench_model_modal_durable_session_sha256": "sha256:" + "5" * 63 + "1",
            "workbench_model_modal_durable_validation_receipt_sha256": "sha256:"
            + "5" * 63
            + "2",
            "workbench_model_modal_durable_report_receipt_sha256": "sha256:"
            + "5" * 63
            + "3",
            "workbench_model_modal_durable_inspect_sha256": "sha256:" + "5" * 63 + "4",
        }
    )
    return receipt, manifest


def valid_v93_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v92_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v93",
            "model_ir_frame3d_rigid_offset_linear_cpu_surface_passed": True,
            "model_ir_frame3d_rigid_offset_linear_cpu_restart_bitwise_passed": True,
            "model_ir_frame3d_rigid_offset_linear_cpu_fallback_count": 0,
            "model_ir_frame3d_rigid_offset_model_sha256": "sha256:" + "6" * 63 + "1",
            "model_ir_frame3d_rigid_offset_request_sha256": "sha256:" + "6" * 63 + "2",
            "model_ir_frame3d_rigid_offset_result_ir_sha256": "sha256:"
            + "6" * 63
            + "3",
            "model_ir_frame3d_rigid_offset_recovery_sha256": "sha256:" + "6" * 63 + "4",
            "model_ir_frame3d_rigid_offset_checkpoint_sha256": "sha256:"
            + "6" * 63
            + "5",
        }
    )
    return receipt, manifest


def valid_v94_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v93_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v94",
            "model_ir_frame3d_end_release_linear_cpu_surface_passed": True,
            "model_ir_frame3d_end_release_linear_cpu_restart_bitwise_passed": True,
            "model_ir_frame3d_end_release_linear_cpu_fallback_count": 0,
            "model_ir_frame3d_end_release_released_force_exact_zero_passed": True,
            "model_ir_frame3d_end_release_model_sha256": "sha256:" + "7" * 63 + "1",
            "model_ir_frame3d_end_release_request_sha256": "sha256:" + "7" * 63 + "2",
            "model_ir_frame3d_end_release_result_ir_sha256": "sha256:" + "7" * 63 + "3",
            "model_ir_frame3d_end_release_recovery_sha256": "sha256:" + "7" * 63 + "4",
            "model_ir_frame3d_end_release_checkpoint_sha256": "sha256:"
            + "7" * 63
            + "5",
        }
    )
    return receipt, manifest


def valid_v95_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v94_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v95",
            "model_ir_self_weight_linear_cpu_surface_passed": True,
            "model_ir_self_weight_linear_cpu_restart_bitwise_passed": True,
            "model_ir_self_weight_linear_cpu_fallback_count": 0,
            "model_ir_self_weight_standard_gravity_passed": True,
            "model_ir_self_weight_closed_form_tip_displacement_passed": True,
            "model_ir_self_weight_model_sha256": "sha256:" + "8" * 63 + "1",
            "model_ir_self_weight_request_sha256": "sha256:" + "8" * 63 + "2",
            "model_ir_self_weight_result_ir_sha256": "sha256:" + "8" * 63 + "3",
            "model_ir_self_weight_recovery_sha256": "sha256:" + "8" * 63 + "4",
            "model_ir_self_weight_reaction_sha256": "sha256:" + "8" * 63 + "5",
            "model_ir_self_weight_checkpoint_sha256": "sha256:" + "8" * 63 + "6",
        }
    )
    return receipt, manifest


def valid_v96_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v95_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v96",
            "model_ir_frame3d_member_distributed_load_linear_cpu_surface_passed": True,
            "model_ir_frame3d_member_distributed_load_linear_cpu_restart_bitwise_passed": True,
            "model_ir_frame3d_member_distributed_load_linear_cpu_fallback_count": 0,
            "model_ir_frame3d_member_distributed_load_fixed_end_force_passed": True,
            "model_ir_frame3d_member_distributed_load_closed_form_tip_displacement_passed": True,
            "model_ir_frame3d_member_distributed_load_model_sha256": "sha256:"
            + "9" * 63
            + "1",
            "model_ir_frame3d_member_distributed_load_request_sha256": "sha256:"
            + "9" * 63
            + "2",
            "model_ir_frame3d_member_distributed_load_result_ir_sha256": "sha256:"
            + "9" * 63
            + "3",
            "model_ir_frame3d_member_distributed_load_recovery_sha256": "sha256:"
            + "9" * 63
            + "4",
            "model_ir_frame3d_member_distributed_load_reaction_sha256": "sha256:"
            + "9" * 63
            + "5",
            "model_ir_frame3d_member_distributed_load_checkpoint_sha256": "sha256:"
            + "9" * 63
            + "6",
        }
    )
    return receipt, manifest


def valid_v97_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v96_contract()
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v97",
            "model_ir_frame3d_prescribed_support_linear_cpu_surface_passed": True,
            "model_ir_frame3d_prescribed_support_linear_cpu_restart_bitwise_passed": True,
            "model_ir_frame3d_prescribed_support_linear_cpu_fallback_count": 0,
            "model_ir_frame3d_prescribed_support_effective_rhs_passed": True,
            "model_ir_frame3d_prescribed_support_terminal_displacement_passed": True,
            "model_ir_frame3d_prescribed_support_reaction_passed": True,
            "model_ir_frame3d_prescribed_support_model_sha256": "sha256:"
            + "a" * 63
            + "1",
            "model_ir_frame3d_prescribed_support_edit_receipt_sha256": "sha256:"
            + "a" * 63
            + "2",
            "model_ir_frame3d_prescribed_support_combination_receipt_sha256": "sha256:"
            + "a" * 63
            + "3",
            "model_ir_frame3d_prescribed_support_request_sha256": "sha256:"
            + "a" * 63
            + "4",
            "model_ir_frame3d_prescribed_support_result_ir_sha256": "sha256:"
            + "a" * 63
            + "5",
            "model_ir_frame3d_prescribed_support_recovery_sha256": "sha256:"
            + "a" * 63
            + "6",
            "model_ir_frame3d_prescribed_support_reaction_sha256": "sha256:"
            + "a" * 63
            + "7",
            "model_ir_frame3d_prescribed_support_checkpoint_sha256": "sha256:"
            + "a" * 63
            + "8",
        }
    )
    return receipt, manifest


def valid_v98_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v97_contract()
    identities = [f"sha256:{index:064x}" for index in range(201, 213)]
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v98",
            "workbench_model_buckling_request_create_surface_passed": True,
            "model_ir_buckling_product_surface_passed": True,
            "model_ir_buckling_repeat_bitwise_passed": True,
            "model_ir_buckling_restart_surface_passed": True,
            "model_ir_buckling_restart_bitwise_passed": True,
            "workbench_model_buckling_result_view_surface_passed": True,
            "workbench_model_buckling_result_view_read_only_passed": True,
            "workbench_model_buckling_result_view_invalid_window_rejected": True,
            "workbench_model_buckling_durable_session_surface_passed": True,
            "workbench_model_buckling_durable_session_crash_reconciliation_passed": True,
            "workbench_model_buckling_durable_session_restart_bitwise_passed": True,
            "workbench_model_buckling_durable_session_tamper_rejected": True,
            "workbench_model_buckling_durable_session_null_authority_passed": True,
            "model_ir_buckling_mode_count": 2,
            "model_ir_buckling_active_dof_count": 6,
            "model_ir_buckling_fallback_count": 0,
            "model_ir_buckling_model_sha256": identities[0],
            "model_ir_buckling_request_sha256": identities[1],
            "workbench_model_buckling_request_receipt_sha256": identities[2],
            "model_ir_buckling_checkpoint_sha256": identities[3],
            "model_ir_buckling_result_ir_sha256": identities[4],
            "model_ir_buckling_run_receipt_sha256": identities[5],
            "workbench_model_buckling_result_view_en_us_sha256": identities[6],
            "workbench_model_buckling_result_view_ko_kr_sha256": identities[7],
            "workbench_model_buckling_durable_session_sha256": identities[8],
            "workbench_model_buckling_durable_validation_receipt_sha256": identities[9],
            "workbench_model_buckling_durable_report_receipt_sha256": identities[10],
            "workbench_model_buckling_durable_inspect_sha256": identities[11],
        }
    )
    return receipt, manifest


def valid_v99_contract() -> tuple[dict, dict]:
    receipt, manifest = valid_v98_contract()
    identities = [f"sha256:{index:064x}" for index in range(213, 217)]
    receipt.update(
        {
            "schema_version": "structural-native-distribution-e2e.v99",
            "model_ir_buckling_durable_job_surface_passed": True,
            "model_ir_buckling_durable_job_idempotency_passed": True,
            "model_ir_buckling_durable_job_process_restart_passed": True,
            "model_ir_buckling_durable_job_exact_product_parity_passed": True,
            "model_ir_buckling_durable_job_overwrite_rejected": True,
            "model_ir_buckling_durable_job_blob_tamper_rejected": True,
            "model_ir_buckling_http_service_surface_passed": True,
            "model_ir_buckling_http_named_artifact_parity_passed": True,
            "model_ir_buckling_durable_job_artifact_count": 18,
            "model_ir_buckling_durable_job_request_envelope_sha256": identities[0],
            "model_ir_buckling_durable_job_terminal_event_sha256": identities[1],
            "model_ir_buckling_durable_job_export_receipt_sha256": identities[2],
            "model_ir_buckling_http_service_receipt_sha256": identities[3],
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
    assert any(
        "workbench_catalog_surface_passed" in error for error in validation["errors"]
    )


def test_distribution_receipt_accepts_native_evidence_builder_v5_contract(
    tmp_path: Path,
):
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
    assert any(
        "evidence_builder_build_passed" in error for error in validation["errors"]
    )


def test_distribution_receipt_accepts_native_catalog_builder_v6_contract(
    tmp_path: Path,
):
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
    assert any(
        "catalog_builder_check_passed" in error for error in validation["errors"]
    )


def test_distribution_receipt_accepts_localized_pdf_v7_contract(tmp_path: Path):
    receipt, manifest = valid_v7_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_missing_v7_localized_pdf_authority(
    tmp_path: Path,
):
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
        "workbench_model_view_surface_passed" in error for error in validation["errors"]
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
        "workbench_model_edit_surface_passed" in error for error in validation["errors"]
    )


def test_distribution_receipt_rejects_invalid_v9_model_edit_identity(tmp_path: Path):
    receipt, manifest = valid_v9_contract()
    receipt["workbench_model_edit_receipt_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_model_edit_receipt_sha256" in error for error in validation["errors"]
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
    assert any(
        "response-view identities must differ" in error
        for error in validation["errors"]
    )
    assert any(
        "deformed-view identities must differ" in error
        for error in validation["errors"]
    )


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
    assert any(
        "model-view identities must differ" in error for error in validation["errors"]
    )


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
        "model_ir_linear_report_pdf_sha256" in error for error in validation["errors"]
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


def test_distribution_receipt_accepts_constraint_value_edit_v18_contract(
    tmp_path: Path,
):
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


def test_distribution_receipt_accepts_linear_load_pattern_add_v26_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v26_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v26_linear_load_pattern_add(
    tmp_path: Path,
):
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


def test_distribution_receipt_accepts_frame_element_properties_v29_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v29_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v29_frame_element_properties(
    tmp_path: Path,
):
    receipt, manifest = valid_v29_contract()
    receipt["workbench_frame_element_properties_edit_surface_passed"] = False
    receipt["workbench_frame_element_properties_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
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


def test_distribution_receipt_accepts_truss3d_leaf_deletion_v32_contract(
    tmp_path: Path,
):
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


def test_distribution_receipt_accepts_frame3d_leaf_deletion_v33_contract(
    tmp_path: Path,
):
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


def test_distribution_receipt_accepts_fixed_constraint_delete_v34_contract(
    tmp_path: Path,
):
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


def test_distribution_receipt_accepts_orphan_node_delete_v41_contract(tmp_path: Path):
    receipt, manifest = valid_v41_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v41_orphan_node_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v41_contract()
    receipt["workbench_orphan_node_delete_surface_passed"] = False
    receipt["workbench_orphan_node_delete_model_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_orphan_node_delete_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_orphan_node_delete_model_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_load_combination_add_v42_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v42_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v42_linear_load_combination_add(
    tmp_path: Path,
):
    receipt, manifest = valid_v42_contract()
    receipt["workbench_linear_load_combination_add_surface_passed"] = False
    receipt["workbench_linear_load_combination_add_solver_rejection_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_load_combination_add_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_load_combination_add_solver_rejection_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_load_combination_delete_v43_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v43_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v43_linear_load_combination_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v43_contract()
    receipt["workbench_linear_load_combination_delete_surface_passed"] = False
    receipt["workbench_linear_load_combination_delete_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_load_combination_delete_surface_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_load_combination_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_load_combination_execution_v44_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v44_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v44_linear_load_combination_execution(
    tmp_path: Path,
):
    receipt, manifest = valid_v44_contract()
    receipt["workbench_linear_load_combination_restart_passed"] = False
    receipt["workbench_linear_load_combination_assembly_receipt_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_load_combination_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_load_combination_assembly_receipt_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_direct_linear_load_combination_v45_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v45_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v45_direct_linear_load_combination(
    tmp_path: Path,
):
    receipt, manifest = valid_v45_contract()
    receipt["workbench_direct_linear_load_combination_restart_passed"] = False
    receipt["workbench_direct_linear_load_combination_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_direct_linear_load_combination_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_direct_linear_load_combination_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nested_linear_load_combination_v46_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v46_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v46_nested_linear_load_combination(
    tmp_path: Path,
):
    receipt, manifest = valid_v46_contract()
    receipt["workbench_nested_linear_load_combination_restart_passed"] = False
    receipt["workbench_nested_linear_load_combination_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nested_linear_load_combination_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nested_linear_load_combination_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_direct_linear_load_combination_delete_v47_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v47_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v47_direct_linear_load_combination_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v47_contract()
    receipt["workbench_direct_linear_load_combination_delete_restart_passed"] = False
    receipt["workbench_direct_linear_load_combination_delete_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_direct_linear_load_combination_delete_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_direct_linear_load_combination_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nested_linear_load_combination_delete_v48_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v48_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v48_nested_linear_load_combination_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v48_contract()
    receipt["workbench_nested_linear_load_combination_delete_restart_passed"] = False
    receipt["workbench_nested_linear_load_combination_delete_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nested_linear_load_combination_delete_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nested_linear_load_combination_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_direct_linear_load_combination_factor_edit_v49_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v49_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v49_direct_factor_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v49_contract()
    receipt["workbench_direct_linear_load_combination_factor_edit_restart_passed"] = (
        False
    )
    receipt["workbench_direct_linear_load_combination_factor_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_direct_linear_load_combination_factor_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_direct_linear_load_combination_factor_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nested_linear_load_combination_factor_edit_v50_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v50_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v50_nested_factor_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v50_contract()
    receipt["workbench_nested_linear_load_combination_factor_edit_restart_passed"] = (
        False
    )
    receipt["workbench_nested_linear_load_combination_factor_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nested_linear_load_combination_factor_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nested_linear_load_combination_factor_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_direct_linear_load_combination_reference_edit_v51_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v51_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v51_direct_reference_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v51_contract()
    receipt[
        "workbench_direct_linear_load_combination_reference_edit_restart_passed"
    ] = False
    receipt[
        "workbench_direct_linear_load_combination_reference_edit_recovery_sha256"
    ] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_direct_linear_load_combination_reference_edit_restart_passed"
        in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_direct_linear_load_combination_reference_edit_recovery_sha256"
        in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nested_linear_load_combination_reference_edit_v52_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v52_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v52_nested_reference_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v52_contract()
    receipt[
        "workbench_nested_linear_load_combination_reference_edit_restart_passed"
    ] = False
    receipt[
        "workbench_nested_linear_load_combination_reference_edit_recovery_sha256"
    ] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nested_linear_load_combination_reference_edit_restart_passed"
        in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nested_linear_load_combination_reference_edit_recovery_sha256"
        in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_direct_linear_load_combination_term_add_v53_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v53_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v53_direct_term_add(
    tmp_path: Path,
):
    receipt, manifest = valid_v53_contract()
    receipt["workbench_direct_linear_load_combination_term_add_restart_passed"] = False
    receipt["workbench_direct_linear_load_combination_term_add_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_direct_linear_load_combination_term_add_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_direct_linear_load_combination_term_add_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_direct_linear_load_combination_term_delete_v54_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v54_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v54_direct_term_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v54_contract()
    receipt["workbench_direct_linear_load_combination_term_delete_restart_passed"] = (
        False
    )
    receipt["workbench_direct_linear_load_combination_term_delete_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_direct_linear_load_combination_term_delete_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_direct_linear_load_combination_term_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nested_linear_load_combination_term_add_v55_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v55_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v55_nested_term_add(
    tmp_path: Path,
):
    receipt, manifest = valid_v55_contract()
    receipt["workbench_nested_linear_load_combination_term_add_restart_passed"] = False
    receipt["workbench_nested_linear_load_combination_term_add_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nested_linear_load_combination_term_add_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nested_linear_load_combination_term_add_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nested_linear_load_combination_term_delete_v56_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v56_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v56_nested_term_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v56_contract()
    receipt["workbench_nested_linear_load_combination_term_delete_restart_passed"] = (
        False
    )
    receipt["workbench_nested_linear_load_combination_term_delete_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nested_linear_load_combination_term_delete_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nested_linear_load_combination_term_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nested_linear_load_combination_term_reorder_v57_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v57_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v57_nested_term_reorder(
    tmp_path: Path,
):
    receipt, manifest = valid_v57_contract()
    receipt["workbench_nested_linear_load_combination_term_reorder_restart_passed"] = (
        False
    )
    receipt["workbench_nested_linear_load_combination_term_reorder_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nested_linear_load_combination_term_reorder_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nested_linear_load_combination_term_reorder_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_direct_linear_load_combination_term_reorder_v58_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v58_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v58_direct_term_reorder(
    tmp_path: Path,
):
    receipt, manifest = valid_v58_contract()
    receipt["workbench_direct_linear_load_combination_term_reorder_restart_passed"] = (
        False
    )
    receipt["workbench_direct_linear_load_combination_term_reorder_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_direct_linear_load_combination_term_reorder_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_direct_linear_load_combination_term_reorder_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_direct_linear_load_combination_term_insert_v59_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v59_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v59_direct_term_insert(
    tmp_path: Path,
):
    receipt, manifest = valid_v59_contract()
    receipt["workbench_direct_linear_load_combination_term_insert_restart_passed"] = (
        False
    )
    receipt["workbench_direct_linear_load_combination_term_insert_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_direct_linear_load_combination_term_insert_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_direct_linear_load_combination_term_insert_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nested_linear_load_combination_term_insert_v60_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v60_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v60_nested_term_insert(
    tmp_path: Path,
):
    receipt, manifest = valid_v60_contract()
    receipt["workbench_nested_linear_load_combination_term_insert_restart_passed"] = (
        False
    )
    receipt["workbench_nested_linear_load_combination_term_insert_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nested_linear_load_combination_term_insert_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nested_linear_load_combination_term_insert_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nodal_load_target_edit_v61_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v61_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v61_nodal_load_target_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v61_contract()
    receipt["workbench_nodal_load_target_edit_restart_passed"] = False
    receipt["workbench_nodal_load_target_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nodal_load_target_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nodal_load_target_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_constraint_target_edit_v62_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v62_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v62_constraint_target_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v62_contract()
    receipt["workbench_constraint_target_edit_restart_passed"] = False
    receipt["workbench_constraint_target_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_constraint_target_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_constraint_target_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_fixed_constraint_dof_delete_v63_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v63_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v63_fixed_constraint_dof_delete(
    tmp_path: Path,
):
    receipt, manifest = valid_v63_contract()
    receipt["workbench_fixed_constraint_dof_delete_restart_passed"] = False
    receipt["workbench_fixed_constraint_dof_delete_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_fixed_constraint_dof_delete_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_fixed_constraint_dof_delete_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_fixed_constraint_dof_add_v64_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v64_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v64_fixed_constraint_dof_add(
    tmp_path: Path,
):
    receipt, manifest = valid_v64_contract()
    receipt["workbench_fixed_constraint_dof_add_restart_passed"] = False
    receipt["workbench_fixed_constraint_dof_add_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_fixed_constraint_dof_add_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_fixed_constraint_dof_add_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_fixed_constraint_dof_reorder_v65_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v65_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v65_fixed_constraint_dof_reorder(
    tmp_path: Path,
):
    receipt, manifest = valid_v65_contract()
    receipt["workbench_fixed_constraint_dof_reorder_restart_passed"] = False
    receipt["workbench_fixed_constraint_dof_reorder_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_fixed_constraint_dof_reorder_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_fixed_constraint_dof_reorder_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_fixed_constraint_identity_edit_v66_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v66_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v66_fixed_constraint_identity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v66_contract()
    receipt["workbench_fixed_constraint_identity_edit_restart_passed"] = False
    receipt["workbench_fixed_constraint_identity_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_fixed_constraint_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_fixed_constraint_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_nodal_load_identity_edit_v67_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v67_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v67_nodal_load_identity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v67_contract()
    receipt["workbench_nodal_load_identity_edit_restart_passed"] = False
    receipt["workbench_nodal_load_identity_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_nodal_load_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_nodal_load_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_load_pattern_identity_edit_v68_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v68_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v68_linear_load_pattern_identity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v68_contract()
    receipt["workbench_linear_load_pattern_identity_edit_restart_passed"] = False
    receipt["workbench_linear_load_pattern_identity_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_load_pattern_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_load_pattern_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_material_identity_edit_v69_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v69_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v69_linear_material_identity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v69_contract()
    receipt["workbench_linear_material_identity_edit_restart_passed"] = False
    receipt["workbench_linear_material_identity_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_material_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_material_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame_section_identity_edit_v70_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v70_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v70_frame_section_identity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v70_contract()
    receipt["workbench_frame_section_identity_edit_restart_passed"] = False
    receipt["workbench_frame_section_identity_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_frame_section_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_frame_section_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_truss_section_identity_edit_v71_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v71_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v71_truss_section_identity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v71_contract()
    receipt["workbench_truss_section_identity_edit_restart_passed"] = False
    receipt["workbench_truss_section_identity_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_truss_section_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_truss_section_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_node_identity_edit_v72_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v72_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v72_node_identity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v72_contract()
    receipt["workbench_node_identity_edit_restart_passed"] = False
    receipt["workbench_node_identity_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_node_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_node_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_element_identity_edit_v73_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v73_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v73_element_identity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v73_contract()
    receipt["workbench_element_identity_edit_restart_passed"] = False
    receipt["workbench_element_identity_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_element_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_element_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_load_combination_identity_edit_v74_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v74_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v74_linear_load_combination_identity_edit(
    tmp_path: Path,
):
    receipt, manifest = valid_v74_contract()
    receipt["workbench_linear_load_combination_identity_edit_restart_passed"] = False
    receipt["workbench_linear_load_combination_identity_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_load_combination_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_load_combination_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_model_identity_edit_v75_contract(tmp_path: Path):
    receipt, manifest = valid_v75_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v75_model_identity_edit(tmp_path: Path):
    receipt, manifest = valid_v75_contract()
    receipt["workbench_model_identity_edit_restart_passed"] = False
    receipt["workbench_model_identity_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_model_identity_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_model_identity_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_node_identity_cascade_v76_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v76_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v76_node_identity_cascade(
    tmp_path: Path,
):
    receipt, manifest = valid_v76_contract()
    receipt["workbench_node_identity_cascade_edit_restart_passed"] = False
    receipt["workbench_node_identity_cascade_edit_recovery_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_node_identity_cascade_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_node_identity_cascade_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame_section_identity_cascade_v77_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v77_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v77_frame_section_identity_cascade(
    tmp_path: Path,
):
    receipt, manifest = valid_v77_contract()
    receipt["workbench_frame_section_identity_cascade_edit_restart_passed"] = False
    receipt["workbench_frame_section_identity_cascade_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_frame_section_identity_cascade_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_frame_section_identity_cascade_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_material_identity_cascade_v78_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v78_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v78_linear_material_identity_cascade(
    tmp_path: Path,
):
    receipt, manifest = valid_v78_contract()
    receipt["workbench_linear_material_identity_cascade_edit_restart_passed"] = False
    receipt["workbench_linear_material_identity_cascade_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_material_identity_cascade_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_material_identity_cascade_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_truss_section_identity_cascade_v79_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v79_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v79_truss_section_identity_cascade(
    tmp_path: Path,
):
    receipt, manifest = valid_v79_contract()
    receipt["workbench_truss_section_identity_cascade_edit_restart_passed"] = False
    receipt["workbench_truss_section_identity_cascade_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_truss_section_identity_cascade_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_truss_section_identity_cascade_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_load_pattern_identity_cascade_v80_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v80_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v80_load_pattern_identity_cascade(
    tmp_path: Path,
):
    receipt, manifest = valid_v80_contract()
    receipt["workbench_linear_load_pattern_identity_cascade_edit_restart_passed"] = (
        False
    )
    receipt["workbench_linear_load_pattern_identity_cascade_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_load_pattern_identity_cascade_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_load_pattern_identity_cascade_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_load_combination_identity_cascade_v81_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v81_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v81_load_combination_identity_cascade(
    tmp_path: Path,
):
    receipt, manifest = valid_v81_contract()
    receipt[
        "workbench_linear_load_combination_identity_cascade_edit_restart_passed"
    ] = False
    receipt[
        "workbench_linear_load_combination_identity_cascade_edit_recovery_sha256"
    ] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_linear_load_combination_identity_cascade_edit_restart_passed"
        in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_linear_load_combination_identity_cascade_edit_recovery_sha256"
        in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_element_identity_cascade_v82_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v82_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v82_element_identity_cascade(
    tmp_path: Path,
):
    receipt, manifest = valid_v82_contract()
    receipt["workbench_element_identity_cascade_edit_restart_passed"] = False
    receipt["workbench_element_identity_cascade_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_element_identity_cascade_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_element_identity_cascade_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_fixed_constraint_identity_cascade_v83_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v83_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v83_fixed_constraint_identity_cascade(
    tmp_path: Path,
):
    receipt, manifest = valid_v83_contract()
    receipt["workbench_fixed_constraint_identity_cascade_edit_restart_passed"] = False
    receipt["workbench_fixed_constraint_identity_cascade_edit_recovery_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_fixed_constraint_identity_cascade_edit_restart_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_fixed_constraint_identity_cascade_edit_recovery_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_reaction_result_v84_contract(tmp_path: Path):
    receipt, manifest = valid_v84_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v84_reaction_result(tmp_path: Path):
    receipt, manifest = valid_v84_contract()
    receipt["model_ir_linear_reaction_result_ir_sha256"] = "sha256:INVALID"
    receipt["mgt_model_ir_linear_reaction_result_ir_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_linear_reaction_result_ir_sha256" in error
        for error in validation["errors"]
    )
    assert any(
        "mgt_model_ir_linear_reaction_result_ir_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_reaction_view_v85_contract(tmp_path: Path):
    receipt, manifest = valid_v85_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v85_reaction_view(tmp_path: Path):
    receipt, manifest = valid_v85_contract()
    receipt["model_ir_linear_reaction_view_restart_parity_passed"] = False
    receipt["mgt_model_ir_linear_reaction_view_en_us_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_linear_reaction_view_restart_parity_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "mgt_model_ir_linear_reaction_view_en_us_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_colliding_v85_reaction_view_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v85_contract()
    receipt["model_ir_linear_reaction_view_ko_kr_sha256"] = receipt[
        "model_ir_linear_reaction_view_en_us_sha256"
    ]
    receipt["model_ir_linear_reaction_view_window_sha256"] = receipt[
        "model_ir_linear_reaction_view_en_us_sha256"
    ]
    receipt["mgt_model_ir_linear_reaction_view_ko_kr_sha256"] = receipt[
        "mgt_model_ir_linear_reaction_view_en_us_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "locale identities must differ" in error for error in validation["errors"]
    )
    assert any("window identity must differ" in error for error in validation["errors"])


def test_distribution_receipt_accepts_reaction_audit_v86_contract(tmp_path: Path):
    receipt, manifest = valid_v86_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v86_reaction_audit(tmp_path: Path):
    receipt, manifest = valid_v86_contract()
    receipt["model_ir_linear_reaction_audit_restart_parity_passed"] = False
    receipt["mgt_model_ir_linear_reaction_audit_en_us_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_linear_reaction_audit_restart_parity_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "mgt_model_ir_linear_reaction_audit_en_us_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_colliding_v86_reaction_audit_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v86_contract()
    receipt["model_ir_linear_reaction_audit_ko_kr_sha256"] = receipt[
        "model_ir_linear_reaction_audit_en_us_sha256"
    ]
    receipt["mgt_model_ir_linear_reaction_audit_ko_kr_sha256"] = receipt[
        "mgt_model_ir_linear_reaction_audit_en_us_sha256"
    ]
    receipt["mgt_model_ir_linear_reaction_audit_en_us_sha256"] = receipt[
        "model_ir_linear_reaction_audit_en_us_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "reaction audit locale identities must differ" in error
        for error in validation["errors"]
    )
    assert any("strict and MGT" in error for error in validation["errors"])


def test_distribution_receipt_accepts_nodal_displacement_view_v87_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v87_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v87_nodal_displacement_view(
    tmp_path: Path,
):
    receipt, manifest = valid_v87_contract()
    receipt["model_ir_linear_nodal_displacement_view_restart_parity_passed"] = False
    receipt["mgt_model_ir_linear_nodal_displacement_view_en_us_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_linear_nodal_displacement_view_restart_parity_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "mgt_model_ir_linear_nodal_displacement_view_en_us_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_colliding_v87_displacement_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v87_contract()
    receipt["model_ir_linear_nodal_displacement_view_ko_kr_sha256"] = receipt[
        "model_ir_linear_nodal_displacement_view_en_us_sha256"
    ]
    receipt["mgt_model_ir_linear_nodal_displacement_view_en_us_sha256"] = receipt[
        "model_ir_linear_nodal_displacement_view_en_us_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all nodal displacement locale, window, and profile identities must differ"
        in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_deformed_view_v88_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v88_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v88_linear_deformed_view(
    tmp_path: Path,
):
    receipt, manifest = valid_v88_contract()
    receipt["model_ir_linear_deformed_view_restart_parity_passed"] = False
    receipt["mgt_model_ir_linear_deformed_view_en_us_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_linear_deformed_view_restart_parity_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "mgt_model_ir_linear_deformed_view_en_us_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_colliding_v88_deformed_view_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v88_contract()
    receipt["model_ir_linear_deformed_view_projection_sha256"] = receipt[
        "model_ir_linear_deformed_view_en_us_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all linear deformed-view locale, projection, and profile identities must differ"
        in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_linear_element_recovery_view_v89_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v89_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_v89_linear_element_recovery_view(
    tmp_path: Path,
):
    receipt, manifest = valid_v89_contract()
    receipt["model_ir_linear_element_recovery_view_restart_parity_passed"] = False
    receipt["mgt_model_ir_linear_element_recovery_view_en_us_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_linear_element_recovery_view_restart_parity_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "mgt_model_ir_linear_element_recovery_view_en_us_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_colliding_v89_element_recovery_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v89_contract()
    receipt["mgt_model_ir_linear_element_recovery_view_en_us_sha256"] = receipt[
        "model_ir_linear_element_recovery_view_en_us_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all linear element-recovery-view locale and profile identities must differ"
        in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_model_ir_modal_v90_contract(tmp_path: Path):
    receipt, manifest = valid_v90_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_accepts_model_ir_modal_restart_view_v91_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v91_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_accepts_durable_modal_workbench_v92_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v92_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_accepts_frame3d_rigid_offset_v93_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v93_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_accepts_frame3d_end_release_v94_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v94_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_accepts_model_ir_self_weight_v95_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v95_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_model_ir_self_weight_v95(
    tmp_path: Path,
):
    receipt, manifest = valid_v95_contract()
    receipt["model_ir_self_weight_standard_gravity_passed"] = False
    receipt["model_ir_self_weight_linear_cpu_fallback_count"] = True
    receipt["model_ir_self_weight_checkpoint_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("standard_gravity_passed" in error for error in validation["errors"])
    assert any("fallback_count" in error for error in validation["errors"])
    assert any("checkpoint_sha256" in error for error in validation["errors"])


def test_distribution_receipt_rejects_colliding_model_ir_self_weight_v95_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v95_contract()
    receipt["model_ir_self_weight_reaction_sha256"] = receipt[
        "model_ir_self_weight_result_ir_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all installed ModelIR self-weight identities must differ" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame3d_member_distributed_load_v96_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v96_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_frame3d_member_distributed_load_v96(
    tmp_path: Path,
):
    receipt, manifest = valid_v96_contract()
    receipt["model_ir_frame3d_member_distributed_load_fixed_end_force_passed"] = False
    receipt["model_ir_frame3d_member_distributed_load_linear_cpu_fallback_count"] = True
    receipt["model_ir_frame3d_member_distributed_load_checkpoint_sha256"] = (
        "sha256:INVALID"
    )
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("fixed_end_force_passed" in error for error in validation["errors"])
    assert any("fallback_count" in error for error in validation["errors"])
    assert any("checkpoint_sha256" in error for error in validation["errors"])


def test_distribution_receipt_rejects_colliding_frame3d_member_distributed_load_v96_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v96_contract()
    receipt["model_ir_frame3d_member_distributed_load_reaction_sha256"] = receipt[
        "model_ir_frame3d_member_distributed_load_result_ir_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all installed ModelIR Frame3D member distributed load identities must differ"
        in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame3d_prescribed_support_v97_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v97_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_frame3d_prescribed_support_v97(
    tmp_path: Path,
):
    receipt, manifest = valid_v97_contract()
    receipt["model_ir_frame3d_prescribed_support_effective_rhs_passed"] = False
    receipt["model_ir_frame3d_prescribed_support_linear_cpu_fallback_count"] = True
    receipt["model_ir_frame3d_prescribed_support_checkpoint_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("effective_rhs_passed" in error for error in validation["errors"])
    assert any("fallback_count" in error for error in validation["errors"])
    assert any("checkpoint_sha256" in error for error in validation["errors"])


def test_distribution_receipt_rejects_colliding_frame3d_prescribed_support_v97_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v97_contract()
    receipt["model_ir_frame3d_prescribed_support_reaction_sha256"] = receipt[
        "model_ir_frame3d_prescribed_support_result_ir_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all installed ModelIR Frame3D prescribed support identities must differ"
        in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame3d_linear_buckling_v98_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v98_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_unbound_frame3d_linear_buckling_v98(
    tmp_path: Path,
):
    receipt, manifest = valid_v98_contract()
    receipt["workbench_model_buckling_durable_session_tamper_rejected"] = False
    receipt["model_ir_buckling_fallback_count"] = True
    receipt["model_ir_buckling_checkpoint_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("tamper_rejected" in error for error in validation["errors"])
    assert any("fallback_count" in error for error in validation["errors"])
    assert any("checkpoint_sha256" in error for error in validation["errors"])


def test_distribution_receipt_rejects_colliding_frame3d_linear_buckling_v98_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v98_contract()
    receipt["model_ir_buckling_result_ir_sha256"] = receipt[
        "model_ir_buckling_checkpoint_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all installed ModelIR Frame3D linear-buckling identities must differ"
        in error
        for error in validation["errors"]
    )


def test_distribution_receipt_accepts_frame3d_linear_buckling_job_service_v99_contract(
    tmp_path: Path,
):
    receipt, manifest = valid_v99_contract()
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 0, completed.stderr
    validation = json.loads(completed.stdout)
    assert validation["valid"] is True
    assert validation["authoritative"] is True


def test_distribution_receipt_rejects_weakened_frame3d_linear_buckling_job_service_v99(
    tmp_path: Path,
):
    receipt, manifest = valid_v99_contract()
    receipt["model_ir_buckling_durable_job_blob_tamper_rejected"] = False
    receipt["model_ir_buckling_durable_job_artifact_count"] = 17
    receipt["model_ir_buckling_http_service_receipt_sha256"] = receipt[
        "model_ir_buckling_durable_job_terminal_event_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("blob_tamper_rejected" in error for error in validation["errors"])
    assert any("artifact_count" in error for error in validation["errors"])
    assert any("identities must differ" in error for error in validation["errors"])


def test_distribution_receipt_rejects_unbound_frame3d_end_release_v94(
    tmp_path: Path,
):
    receipt, manifest = valid_v94_contract()
    receipt["model_ir_frame3d_end_release_released_force_exact_zero_passed"] = False
    receipt["model_ir_frame3d_end_release_linear_cpu_fallback_count"] = True
    receipt["model_ir_frame3d_end_release_checkpoint_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("exact_zero_passed" in error for error in validation["errors"])
    assert any("fallback_count" in error for error in validation["errors"])
    assert any("checkpoint_sha256" in error for error in validation["errors"])


def test_distribution_receipt_rejects_colliding_frame3d_end_release_v94_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v94_contract()
    receipt["model_ir_frame3d_end_release_recovery_sha256"] = receipt[
        "model_ir_frame3d_end_release_result_ir_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all installed Frame3D end-release identities must differ" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_unbound_frame3d_rigid_offset_v93(
    tmp_path: Path,
):
    receipt, manifest = valid_v93_contract()
    receipt["model_ir_frame3d_rigid_offset_linear_cpu_restart_bitwise_passed"] = False
    receipt["model_ir_frame3d_rigid_offset_linear_cpu_fallback_count"] = True
    receipt["model_ir_frame3d_rigid_offset_checkpoint_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any("restart_bitwise_passed" in error for error in validation["errors"])
    assert any("fallback_count" in error for error in validation["errors"])
    assert any("checkpoint_sha256" in error for error in validation["errors"])


def test_distribution_receipt_rejects_colliding_frame3d_rigid_offset_v93_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v93_contract()
    receipt["model_ir_frame3d_rigid_offset_recovery_sha256"] = receipt[
        "model_ir_frame3d_rigid_offset_result_ir_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all installed Frame3D rigid-offset identities must differ" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_unbound_v92_durable_modal_workbench(
    tmp_path: Path,
):
    receipt, manifest = valid_v92_contract()
    receipt["workbench_model_modal_durable_session_tamper_rejected"] = False
    receipt["workbench_model_modal_durable_session_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "workbench_model_modal_durable_session_tamper_rejected" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_model_modal_durable_session_sha256" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_colliding_v92_modal_workbench_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v92_contract()
    receipt["workbench_model_modal_durable_inspect_sha256"] = receipt[
        "workbench_model_modal_durable_session_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all installed durable modal Workbench identities must differ" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_unbound_v91_modal_restart_view(tmp_path: Path):
    receipt, manifest = valid_v91_contract()
    receipt["model_ir_modal_restart_bitwise_passed"] = False
    receipt["workbench_model_modal_result_view_read_only_passed"] = False
    receipt["model_ir_modal_checkpoint_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_modal_restart_bitwise_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "workbench_model_modal_result_view_read_only_passed" in error
        for error in validation["errors"]
    )
    assert any(
        "model_ir_modal_checkpoint_sha256" in error for error in validation["errors"]
    )


def test_distribution_receipt_rejects_colliding_v91_modal_view_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v91_contract()
    receipt["workbench_model_modal_result_view_ko_kr_sha256"] = receipt[
        "workbench_model_modal_result_view_en_us_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all installed ModelIR modal restart/view identities must differ" in error
        for error in validation["errors"]
    )


def test_distribution_receipt_rejects_unbound_v90_model_ir_modal_product(
    tmp_path: Path,
):
    receipt, manifest = valid_v90_contract()
    receipt["model_ir_modal_repeat_bitwise_passed"] = False
    receipt["model_ir_modal_mode_count"] = 2
    receipt["model_ir_modal_result_ir_sha256"] = "sha256:INVALID"
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "model_ir_modal_repeat_bitwise_passed" in error
        for error in validation["errors"]
    )
    assert any("model_ir_modal_mode_count" in error for error in validation["errors"])
    assert any(
        "model_ir_modal_result_ir_sha256" in error for error in validation["errors"]
    )


def test_distribution_receipt_rejects_colliding_v90_model_ir_modal_identities(
    tmp_path: Path,
):
    receipt, manifest = valid_v90_contract()
    receipt["model_ir_modal_report_ir_sha256"] = receipt[
        "model_ir_modal_result_ir_sha256"
    ]
    completed = run_checker(tmp_path, receipt, manifest)
    assert completed.returncode == 1
    validation = json.loads(completed.stdout)
    assert any(
        "all installed ModelIR modal artifact identities must differ" in error
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
        "structural-native-rootfs-isolation-e2e.v7",
        "structural-native-rootfs-isolation-e2e.v8",
        "structural-native-rootfs-isolation-e2e.v9",
        "structural-native-rootfs-isolation-e2e.v10",
        "structural-native-rootfs-isolation-e2e.v11",
        "structural-native-rootfs-isolation-e2e.v12",
        "structural-native-rootfs-isolation-e2e.v13",
        "structural-native-rootfs-isolation-e2e.v14",
        "structural-native-rootfs-isolation-e2e.v15",
        "structural-native-rootfs-isolation-e2e.v16",
        "structural-native-rootfs-isolation-e2e.v17",
        "structural-native-rootfs-isolation-e2e.v18",
        "structural-native-rootfs-isolation-e2e.v19",
        "structural-native-rootfs-isolation-e2e.v20",
        "structural-native-rootfs-isolation-e2e.v21",
        "model_ir_linear_result_recovery_ir_sha256",
        "model_ir_linear_reaction_result_ir_sha256",
        "model_ir_linear_pdf_receipt_sha256",
        "model_ir_linear_localized_pdf_surface_passed",
        "model_ir_linear_localized_pdf_en_us_sha256",
        "mgt_model_ir_linear_source_sha256",
        "mgt_model_ir_linear_import_health_sha256",
        "mgt_model_ir_linear_result_recovery_ir_sha256",
        "mgt_model_ir_linear_reaction_result_ir_sha256",
        "model_ir_linear_reaction_view_en_us_sha256",
        "mgt_model_ir_linear_reaction_view_en_us_sha256",
        "workbench_reaction_view_wrong_profile_rejected",
        "validate_rootfs_isolation_evidence_v8",
        "model_ir_linear_reaction_audit_en_us_sha256",
        "mgt_model_ir_linear_reaction_audit_en_us_sha256",
        "workbench_reaction_audit_wrong_profile_rejected",
        "validate_rootfs_isolation_evidence_v9",
        "model_ir_linear_nodal_displacement_view_en_us_sha256",
        "model_ir_linear_nodal_displacement_view_window_sha256",
        "mgt_model_ir_linear_nodal_displacement_view_en_us_sha256",
        "workbench_nodal_displacement_view_wrong_profile_rejected",
        "inspect_rootfs_nodal_displacement_view_surface",
        "validate_rootfs_isolation_evidence_v10",
        "model_ir_linear_deformed_view_en_us_sha256",
        "model_ir_linear_deformed_view_projection_sha256",
        "mgt_model_ir_linear_deformed_view_en_us_sha256",
        "workbench_linear_deformed_view_invalid_step_rejected",
        "inspect_rootfs_linear_deformed_view_surface",
        "validate_rootfs_isolation_evidence_v11",
        "model_ir_linear_element_recovery_view_en_us_sha256",
        "mgt_model_ir_linear_element_recovery_view_en_us_sha256",
        "workbench_linear_element_recovery_view_invalid_window_rejected",
        "inspect_rootfs_linear_element_recovery_view_surface",
        "validate_rootfs_isolation_evidence_v12",
        "model_ir_modal_checkpoint_sha256",
        "workbench_model_modal_result_view_en_us_sha256",
        "inspect_rootfs_model_modal_surface",
        "validate_rootfs_isolation_evidence_v13",
        "workbench_model_modal_durable_session_sha256",
        "workbench_model_modal_durable_session_crash_reconciliation_passed",
        "inspect_rootfs_model_modal_workbench_surface",
        "validate_rootfs_isolation_evidence_v14",
        "model_ir_frame3d_rigid_offset_linear_cpu_surface_passed",
        "model_ir_frame3d_rigid_offset_recovery_sha256",
        "inspect_rootfs_frame3d_rigid_offset_surface",
        "validate_rootfs_isolation_evidence_v15",
        "model_ir_frame3d_end_release_linear_cpu_surface_passed",
        "model_ir_frame3d_end_release_released_force_exact_zero_passed",
        "inspect_rootfs_frame3d_end_release_surface",
        "validate_rootfs_isolation_evidence_v16",
        "model_ir_self_weight_linear_cpu_surface_passed",
        "model_ir_self_weight_standard_gravity_passed",
        "inspect_rootfs_frame3d_self_weight_surface",
        "validate_rootfs_isolation_evidence_v17",
        "inspect_rootfs_model_buckling_surface",
        "inspect_rootfs_model_buckling_workbench_surface",
        "model_ir_buckling_mode_count",
        "workbench_model_buckling_durable_session_tamper_rejected",
        "validate_rootfs_isolation_evidence_v20",
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
    assert (
        'frame3d_quickstart_share="$payload/share/structural-examples/frame3d-linear-cantilever"'
        in build
    )
    assert "native/examples/frame3d-linear-cantilever/README.md" in build
    assert "frame_cantilever_all_modes.json" in build
    assert "frame_cantilever_weak_request.json" in build
    assert "frame_cantilever_external_v1.json" in build
    assert "frame_cantilever_language_neutral_oracle_v1.txt" in build
    assert '"$1" == "--check"' in evidence_wrapper
    assert "structural-evidence -- check --root" in evidence_wrapper
    assert 'if [[ "$#" -ne 0 ]]' in evidence_wrapper
    assert "structural-evidence -- build" in evidence_wrapper
    assert '"$1" == "--check"' in catalog_wrapper
    assert "structural-catalog -- check --root" in catalog_wrapper
    assert 'if [[ "$#" -ne 0 ]]' in catalog_wrapper
    assert "structural-catalog -- build" in catalog_wrapper
    assert 'PATH="$empty_path"' in e2e
    assert (
        'frame3d_quickstart_share="$active/share/structural-examples/frame3d-linear-cantilever"'
        in e2e
    )
    assert 'linear_model="$frame3d_quickstart_share/model.json"' in e2e
    assert 'linear_external="$frame3d_quickstart_share/external-result.json"' in e2e
    assert (
        'linear_source_artifact="$frame3d_quickstart_share/language-neutral-oracle.txt"'
        in e2e
    )
    assert 'diff -r "$restarted" "$direct"' in e2e
    assert "workflow-mgt" in e2e
    assert 'diff -r "$mgt_restarted" "$mgt_direct"' in e2e
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
    assert "structural-native-distribution-e2e.v41" in e2e
    assert "structural-native-distribution-e2e.v42" in e2e
    assert "structural-native-distribution-e2e.v43" in e2e
    assert "structural-native-distribution-e2e.v44" in e2e
    assert "structural-native-distribution-e2e.v45" in e2e
    assert "structural-native-distribution-e2e.v46" in e2e
    assert "structural-native-distribution-e2e.v47" in e2e
    assert "structural-native-distribution-e2e.v48" in e2e
    assert "structural-native-distribution-e2e.v49" in e2e
    assert "structural-native-distribution-e2e.v50" in e2e
    assert "structural-native-distribution-e2e.v51" in e2e
    assert "structural-native-distribution-e2e.v52" in e2e
    assert "structural-native-distribution-e2e.v53" in e2e
    assert "structural-native-distribution-e2e.v54" in e2e
    assert "structural-native-distribution-e2e.v55" in e2e
    assert "structural-native-distribution-e2e.v56" in e2e
    assert "structural-native-distribution-e2e.v57" in e2e
    assert "structural-native-distribution-e2e.v58" in e2e
    assert "structural-native-distribution-e2e.v59" in e2e
    assert "structural-native-distribution-e2e.v60" in e2e
    assert "structural-native-distribution-e2e.v61" in e2e
    assert "exercise_nodal_load_target_edit_surface" in e2e
    assert "model-edit-nodal-load-target" in e2e
    assert "structural-native:model-edit-nodal-load-target.v1" in e2e
    assert "workbench_nodal_load_target_edit_surface_passed" in e2e
    assert "workbench_nodal_load_target_edit_recovery_sha256" in e2e
    assert "workbench_nodal_load_target_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v62" in e2e
    assert "exercise_constraint_target_edit_surface" in e2e
    assert "model-edit-constraint-target" in e2e
    assert "structural-native:model-edit-constraint-target.v1" in e2e
    assert "workbench_constraint_target_edit_surface_passed" in e2e
    assert "workbench_constraint_target_edit_recovery_sha256" in e2e
    assert "workbench_constraint_target_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v63" in e2e
    assert "exercise_fixed_constraint_dof_delete_surface" in e2e
    assert "model-delete-fixed-constraint-dof" in e2e
    assert "structural-native:model-delete-fixed-constraint-dof.v1" in e2e
    assert "workbench_fixed_constraint_dof_delete_surface_passed" in e2e
    assert "workbench_fixed_constraint_dof_delete_model_sha256" in e2e
    assert "workbench_fixed_constraint_dof_delete_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_dof_delete_request_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_dof_delete_request_sha256" in e2e
    assert "workbench_fixed_constraint_dof_delete_assembly_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_dof_delete_checkpoint_sha256" in e2e
    assert "workbench_fixed_constraint_dof_delete_result_ir_sha256" in e2e
    assert "workbench_fixed_constraint_dof_delete_recovery_sha256" in e2e
    assert "workbench_fixed_constraint_dof_delete_report_ir_sha256" in e2e
    assert "workbench_fixed_constraint_dof_delete_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v64" in e2e
    assert "exercise_fixed_constraint_dof_add_surface" in e2e
    assert "model-add-fixed-constraint-dof" in e2e
    assert "structural-native:model-add-fixed-constraint-dof.v1" in e2e
    assert "workbench_fixed_constraint_dof_add_surface_passed" in e2e
    assert "workbench_fixed_constraint_dof_add_model_sha256" in e2e
    assert "workbench_fixed_constraint_dof_add_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_dof_add_request_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_dof_add_request_sha256" in e2e
    assert "workbench_fixed_constraint_dof_add_assembly_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_dof_add_checkpoint_sha256" in e2e
    assert "workbench_fixed_constraint_dof_add_result_ir_sha256" in e2e
    assert "workbench_fixed_constraint_dof_add_recovery_sha256" in e2e
    assert "workbench_fixed_constraint_dof_add_report_ir_sha256" in e2e
    assert "workbench_fixed_constraint_dof_add_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v65" in e2e
    assert "exercise_fixed_constraint_dof_reorder_surface" in e2e
    assert "model-reorder-fixed-constraint-dof" in e2e
    assert "structural-native:model-reorder-fixed-constraint-dof.v1" in e2e
    assert "workbench_fixed_constraint_dof_reorder_surface_passed" in e2e
    assert "workbench_fixed_constraint_dof_reorder_model_sha256" in e2e
    assert "workbench_fixed_constraint_dof_reorder_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_dof_reorder_request_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_dof_reorder_request_sha256" in e2e
    assert "workbench_fixed_constraint_dof_reorder_assembly_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_dof_reorder_checkpoint_sha256" in e2e
    assert "workbench_fixed_constraint_dof_reorder_result_ir_sha256" in e2e
    assert "workbench_fixed_constraint_dof_reorder_recovery_sha256" in e2e
    assert "workbench_fixed_constraint_dof_reorder_report_ir_sha256" in e2e
    assert "workbench_fixed_constraint_dof_reorder_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v66" in e2e
    assert "exercise_fixed_constraint_identity_edit_surface" in e2e
    assert "model-edit-fixed-constraint-identity" in e2e
    assert "structural-native:model-edit-fixed-constraint-identity.v1" in e2e
    assert "workbench_fixed_constraint_identity_edit_surface_passed" in e2e
    assert "workbench_fixed_constraint_identity_edit_model_sha256" in e2e
    assert "workbench_fixed_constraint_identity_edit_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_identity_edit_request_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_identity_edit_request_sha256" in e2e
    assert "workbench_fixed_constraint_identity_edit_assembly_receipt_sha256" in e2e
    assert "workbench_fixed_constraint_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_fixed_constraint_identity_edit_result_ir_sha256" in e2e
    assert "workbench_fixed_constraint_identity_edit_recovery_sha256" in e2e
    assert "workbench_fixed_constraint_identity_edit_report_ir_sha256" in e2e
    assert "workbench_fixed_constraint_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v67" in e2e
    assert "exercise_nodal_load_identity_edit_surface" in e2e
    assert "model-edit-nodal-load-identity" in e2e
    assert "structural-native:model-edit-nodal-load-identity.v1" in e2e
    assert "workbench_nodal_load_identity_edit_surface_passed" in e2e
    assert "workbench_nodal_load_identity_edit_model_sha256" in e2e
    assert "workbench_nodal_load_identity_edit_receipt_sha256" in e2e
    assert "workbench_nodal_load_identity_edit_request_receipt_sha256" in e2e
    assert "workbench_nodal_load_identity_edit_request_sha256" in e2e
    assert "workbench_nodal_load_identity_edit_assembly_receipt_sha256" in e2e
    assert "workbench_nodal_load_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_nodal_load_identity_edit_result_ir_sha256" in e2e
    assert "workbench_nodal_load_identity_edit_recovery_sha256" in e2e
    assert "workbench_nodal_load_identity_edit_report_ir_sha256" in e2e
    assert "workbench_nodal_load_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v68" in e2e
    assert "exercise_linear_load_pattern_identity_edit_surface" in e2e
    assert "model-edit-linear-load-pattern-identity" in e2e
    assert "structural-native:model-edit-linear-load-pattern-identity.v1" in e2e
    assert "workbench_linear_load_pattern_identity_edit_surface_passed" in e2e
    assert "workbench_linear_load_pattern_identity_edit_model_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_edit_receipt_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_edit_request_receipt_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_edit_request_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_edit_assembly_receipt_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_edit_result_ir_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_edit_recovery_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_edit_report_ir_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v69" in e2e
    assert "exercise_linear_material_identity_edit_surface" in e2e
    assert "model-edit-linear-material-identity" in e2e
    assert "structural-native:model-edit-linear-material-identity.v1" in e2e
    assert "workbench_linear_material_identity_edit_surface_passed" in e2e
    assert "workbench_linear_material_identity_edit_model_sha256" in e2e
    assert "workbench_linear_material_identity_edit_receipt_sha256" in e2e
    assert "workbench_linear_material_identity_edit_request_receipt_sha256" in e2e
    assert "workbench_linear_material_identity_edit_request_sha256" in e2e
    assert "workbench_linear_material_identity_edit_assembly_receipt_sha256" in e2e
    assert "workbench_linear_material_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_linear_material_identity_edit_result_ir_sha256" in e2e
    assert "workbench_linear_material_identity_edit_recovery_sha256" in e2e
    assert "workbench_linear_material_identity_edit_report_ir_sha256" in e2e
    assert "workbench_linear_material_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v70" in e2e
    assert "exercise_frame_section_identity_edit_surface" in e2e
    assert "model-edit-frame-section-identity" in e2e
    assert "structural-native:model-edit-frame-section-identity.v1" in e2e
    assert "workbench_frame_section_identity_edit_surface_passed" in e2e
    assert "workbench_frame_section_identity_edit_model_sha256" in e2e
    assert "workbench_frame_section_identity_edit_receipt_sha256" in e2e
    assert "workbench_frame_section_identity_edit_request_receipt_sha256" in e2e
    assert "workbench_frame_section_identity_edit_request_sha256" in e2e
    assert "workbench_frame_section_identity_edit_assembly_receipt_sha256" in e2e
    assert "workbench_frame_section_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_frame_section_identity_edit_result_ir_sha256" in e2e
    assert "workbench_frame_section_identity_edit_recovery_sha256" in e2e
    assert "workbench_frame_section_identity_edit_report_ir_sha256" in e2e
    assert "workbench_frame_section_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v71" in e2e
    assert "exercise_truss_section_identity_edit_surface" in e2e
    assert "model-edit-truss-section-identity" in e2e
    assert "structural-native:model-edit-truss-section-identity.v1" in e2e
    assert "workbench_truss_section_identity_edit_surface_passed" in e2e
    assert "workbench_truss_section_identity_edit_model_sha256" in e2e
    assert "workbench_truss_section_identity_edit_receipt_sha256" in e2e
    assert "workbench_truss_section_identity_edit_request_receipt_sha256" in e2e
    assert "workbench_truss_section_identity_edit_request_sha256" in e2e
    assert "workbench_truss_section_identity_edit_assembly_receipt_sha256" in e2e
    assert "workbench_truss_section_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_truss_section_identity_edit_result_ir_sha256" in e2e
    assert "workbench_truss_section_identity_edit_recovery_sha256" in e2e
    assert "workbench_truss_section_identity_edit_report_ir_sha256" in e2e
    assert "workbench_truss_section_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v72" in e2e
    assert "exercise_node_identity_edit_surface" in e2e
    assert "model-edit-node-identity" in e2e
    assert "structural-native:model-edit-node-identity.v1" in e2e
    assert "workbench_node_identity_edit_surface_passed" in e2e
    assert "workbench_node_identity_edit_model_sha256" in e2e
    assert "workbench_node_identity_edit_receipt_sha256" in e2e
    assert "workbench_node_identity_edit_request_receipt_sha256" in e2e
    assert "workbench_node_identity_edit_request_sha256" in e2e
    assert "workbench_node_identity_edit_assembly_receipt_sha256" in e2e
    assert "workbench_node_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_node_identity_edit_result_ir_sha256" in e2e
    assert "workbench_node_identity_edit_recovery_sha256" in e2e
    assert "workbench_node_identity_edit_report_ir_sha256" in e2e
    assert "workbench_node_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v73" in e2e
    assert "exercise_element_identity_edit_surface" in e2e
    assert "model-edit-element-identity" in e2e
    assert "structural-native:model-edit-element-identity.v1" in e2e
    assert "workbench_element_identity_edit_surface_passed" in e2e
    assert "workbench_element_identity_edit_model_sha256" in e2e
    assert "workbench_element_identity_edit_receipt_sha256" in e2e
    assert "workbench_element_identity_edit_request_receipt_sha256" in e2e
    assert "workbench_element_identity_edit_request_sha256" in e2e
    assert "workbench_element_identity_edit_assembly_receipt_sha256" in e2e
    assert "workbench_element_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_element_identity_edit_result_ir_sha256" in e2e
    assert "workbench_element_identity_edit_recovery_sha256" in e2e
    assert "workbench_element_identity_edit_report_ir_sha256" in e2e
    assert "workbench_element_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v74" in e2e
    assert "exercise_linear_load_combination_identity_edit_surface" in e2e
    assert "model-edit-linear-load-combination-identity" in e2e
    assert "structural-native:model-edit-linear-load-combination-identity.v1" in e2e
    assert "workbench_linear_load_combination_identity_edit_surface_passed" in e2e
    assert "workbench_linear_load_combination_identity_edit_model_sha256" in e2e
    assert "workbench_linear_load_combination_identity_edit_receipt_sha256" in e2e
    assert (
        "workbench_linear_load_combination_identity_edit_request_receipt_sha256" in e2e
    )
    assert "workbench_linear_load_combination_identity_edit_request_sha256" in e2e
    assert (
        "workbench_linear_load_combination_identity_edit_assembly_receipt_sha256" in e2e
    )
    assert "workbench_linear_load_combination_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_linear_load_combination_identity_edit_result_ir_sha256" in e2e
    assert "workbench_linear_load_combination_identity_edit_recovery_sha256" in e2e
    assert "workbench_linear_load_combination_identity_edit_report_ir_sha256" in e2e
    assert "workbench_linear_load_combination_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v75" in e2e
    assert "exercise_model_identity_edit_surface" in e2e
    assert "model-edit-model-identity" in e2e
    assert "structural-native:model-edit-model-identity.v1" in e2e
    assert "workbench_model_identity_edit_surface_passed" in e2e
    assert "workbench_model_identity_edit_model_sha256" in e2e
    assert "workbench_model_identity_edit_receipt_sha256" in e2e
    assert "workbench_model_identity_edit_request_receipt_sha256" in e2e
    assert "workbench_model_identity_edit_request_sha256" in e2e
    assert "workbench_model_identity_edit_assembly_receipt_sha256" in e2e
    assert "workbench_model_identity_edit_checkpoint_sha256" in e2e
    assert "workbench_model_identity_edit_result_ir_sha256" in e2e
    assert "workbench_model_identity_edit_recovery_sha256" in e2e
    assert "workbench_model_identity_edit_report_ir_sha256" in e2e
    assert "workbench_model_identity_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v76" in e2e
    assert "exercise_node_identity_cascade_edit_surface" in e2e
    assert "model-edit-node-identity-cascade" in e2e
    assert "structural-native:model-edit-node-identity-cascade.v2" in e2e
    assert "workbench_node_identity_cascade_edit_surface_passed" in e2e
    assert "workbench_node_identity_cascade_edit_model_sha256" in e2e
    assert "workbench_node_identity_cascade_edit_receipt_sha256" in e2e
    assert "workbench_node_identity_cascade_edit_request_receipt_sha256" in e2e
    assert "workbench_node_identity_cascade_edit_request_sha256" in e2e
    assert "workbench_node_identity_cascade_edit_assembly_receipt_sha256" in e2e
    assert "workbench_node_identity_cascade_edit_checkpoint_sha256" in e2e
    assert "workbench_node_identity_cascade_edit_result_ir_sha256" in e2e
    assert "workbench_node_identity_cascade_edit_recovery_sha256" in e2e
    assert "workbench_node_identity_cascade_edit_report_ir_sha256" in e2e
    assert "workbench_node_identity_cascade_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v77" in e2e
    assert "exercise_frame_section_identity_cascade_edit_surface" in e2e
    assert "model-edit-frame-section-identity-cascade" in e2e
    assert "structural-native:model-edit-frame-section-identity-cascade.v2" in e2e
    assert "workbench_frame_section_identity_cascade_edit_surface_passed" in e2e
    assert "workbench_frame_section_identity_cascade_edit_model_sha256" in e2e
    assert "workbench_frame_section_identity_cascade_edit_receipt_sha256" in e2e
    assert "workbench_frame_section_identity_cascade_edit_request_receipt_sha256" in e2e
    assert "workbench_frame_section_identity_cascade_edit_request_sha256" in e2e
    assert (
        "workbench_frame_section_identity_cascade_edit_assembly_receipt_sha256" in e2e
    )
    assert "workbench_frame_section_identity_cascade_edit_checkpoint_sha256" in e2e
    assert "workbench_frame_section_identity_cascade_edit_result_ir_sha256" in e2e
    assert "workbench_frame_section_identity_cascade_edit_recovery_sha256" in e2e
    assert "workbench_frame_section_identity_cascade_edit_report_ir_sha256" in e2e
    assert "workbench_frame_section_identity_cascade_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v78" in e2e
    assert "exercise_linear_material_identity_cascade_edit_surface" in e2e
    assert "model-edit-linear-material-identity-cascade" in e2e
    assert "structural-native:model-edit-linear-material-identity-cascade.v2" in e2e
    assert "workbench_linear_material_identity_cascade_edit_surface_passed" in e2e
    assert "workbench_linear_material_identity_cascade_edit_model_sha256" in e2e
    assert "workbench_linear_material_identity_cascade_edit_receipt_sha256" in e2e
    assert (
        "workbench_linear_material_identity_cascade_edit_request_receipt_sha256" in e2e
    )
    assert "workbench_linear_material_identity_cascade_edit_request_sha256" in e2e
    assert (
        "workbench_linear_material_identity_cascade_edit_assembly_receipt_sha256" in e2e
    )
    assert "workbench_linear_material_identity_cascade_edit_checkpoint_sha256" in e2e
    assert "workbench_linear_material_identity_cascade_edit_result_ir_sha256" in e2e
    assert "workbench_linear_material_identity_cascade_edit_recovery_sha256" in e2e
    assert "workbench_linear_material_identity_cascade_edit_report_ir_sha256" in e2e
    assert "workbench_linear_material_identity_cascade_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v79" in e2e
    assert "exercise_truss_section_identity_cascade_edit_surface" in e2e
    assert "model-edit-truss-section-identity-cascade" in e2e
    assert "structural-native:model-edit-truss-section-identity-cascade.v2" in e2e
    assert "workbench_truss_section_identity_cascade_edit_surface_passed" in e2e
    assert "workbench_truss_section_identity_cascade_edit_model_sha256" in e2e
    assert "workbench_truss_section_identity_cascade_edit_receipt_sha256" in e2e
    assert "workbench_truss_section_identity_cascade_edit_request_receipt_sha256" in e2e
    assert "workbench_truss_section_identity_cascade_edit_request_sha256" in e2e
    assert (
        "workbench_truss_section_identity_cascade_edit_assembly_receipt_sha256" in e2e
    )
    assert "workbench_truss_section_identity_cascade_edit_checkpoint_sha256" in e2e
    assert "workbench_truss_section_identity_cascade_edit_result_ir_sha256" in e2e
    assert "workbench_truss_section_identity_cascade_edit_recovery_sha256" in e2e
    assert "workbench_truss_section_identity_cascade_edit_report_ir_sha256" in e2e
    assert "workbench_truss_section_identity_cascade_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v80" in e2e
    assert "exercise_linear_load_pattern_identity_cascade_edit_surface" in e2e
    assert "model-edit-linear-load-pattern-identity-cascade" in e2e
    assert "structural-native:model-edit-linear-load-pattern-identity-cascade.v2" in e2e
    assert "workbench_linear_load_pattern_identity_cascade_edit_surface_passed" in e2e
    assert "workbench_linear_load_pattern_identity_cascade_edit_model_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_cascade_edit_receipt_sha256" in e2e
    assert (
        "workbench_linear_load_pattern_identity_cascade_edit_request_receipt_sha256"
        in e2e
    )
    assert "workbench_linear_load_pattern_identity_cascade_edit_request_sha256" in e2e
    assert (
        "workbench_linear_load_pattern_identity_cascade_edit_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_linear_load_pattern_identity_cascade_edit_checkpoint_sha256" in e2e
    )
    assert "workbench_linear_load_pattern_identity_cascade_edit_result_ir_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_cascade_edit_recovery_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_cascade_edit_report_ir_sha256" in e2e
    assert "workbench_linear_load_pattern_identity_cascade_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v81" in e2e
    assert "exercise_linear_load_combination_identity_cascade_edit_surface" in e2e
    assert "model-edit-linear-load-combination-identity-cascade" in e2e
    assert (
        "structural-native:model-edit-linear-load-combination-identity-cascade.v2"
        in e2e
    )
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_surface_passed" in e2e
    )
    assert "workbench_linear_load_combination_identity_cascade_edit_model_sha256" in e2e
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_receipt_sha256" in e2e
    )
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_request_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_request_sha256" in e2e
    )
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_checkpoint_sha256"
        in e2e
    )
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_result_ir_sha256"
        in e2e
    )
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_recovery_sha256" in e2e
    )
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_report_ir_sha256"
        in e2e
    )
    assert (
        "workbench_linear_load_combination_identity_cascade_edit_restart_passed" in e2e
    )
    assert "structural-native-distribution-e2e.v82" in e2e
    assert "exercise_element_identity_cascade_edit_surface" in e2e
    assert "model-edit-element-identity-cascade" in e2e
    assert "--element E_1 --new-element E1_LINKED" in e2e
    assert "structural-native:model-edit-element-identity-cascade.v2" in e2e
    assert "workbench_element_identity_cascade_edit_surface_passed" in e2e
    assert "workbench_element_identity_cascade_edit_model_sha256" in e2e
    assert "workbench_element_identity_cascade_edit_receipt_sha256" in e2e
    assert "workbench_element_identity_cascade_edit_request_receipt_sha256" in e2e
    assert "workbench_element_identity_cascade_edit_request_sha256" in e2e
    assert "workbench_element_identity_cascade_edit_assembly_receipt_sha256" in e2e
    assert "workbench_element_identity_cascade_edit_checkpoint_sha256" in e2e
    assert "workbench_element_identity_cascade_edit_result_ir_sha256" in e2e
    assert "workbench_element_identity_cascade_edit_recovery_sha256" in e2e
    assert "workbench_element_identity_cascade_edit_report_ir_sha256" in e2e
    assert "workbench_element_identity_cascade_edit_restart_passed" in e2e
    assert "structural-native-distribution-e2e.v83" in e2e
    assert "exercise_fixed_constraint_identity_cascade_edit_surface" in e2e
    assert "model-edit-fixed-constraint-identity-cascade" in e2e
    assert "--constraint C_1 --new-constraint C1_LINKED" in e2e
    assert "structural-native:model-edit-fixed-constraint-identity-cascade.v2" in e2e
    assert "workbench_fixed_constraint_identity_cascade_edit_surface_passed" in e2e
    assert "workbench_fixed_constraint_identity_cascade_edit_model_sha256" in e2e
    assert "workbench_fixed_constraint_identity_cascade_edit_receipt_sha256" in e2e
    assert (
        "workbench_fixed_constraint_identity_cascade_edit_request_receipt_sha256" in e2e
    )
    assert "workbench_fixed_constraint_identity_cascade_edit_request_sha256" in e2e
    assert (
        "workbench_fixed_constraint_identity_cascade_edit_assembly_receipt_sha256"
        in e2e
    )
    assert "workbench_fixed_constraint_identity_cascade_edit_checkpoint_sha256" in e2e
    assert "workbench_fixed_constraint_identity_cascade_edit_result_ir_sha256" in e2e
    assert "workbench_fixed_constraint_identity_cascade_edit_recovery_sha256" in e2e
    assert "workbench_fixed_constraint_identity_cascade_edit_report_ir_sha256" in e2e
    assert "structural-native-distribution-e2e.v84" in e2e
    assert "model_ir_linear_reaction_result_ir_sha256" in e2e
    assert "mgt_model_ir_linear_reaction_result_ir_sha256" in e2e
    assert "04-resume/reaction-result-ir.json" in e2e
    assert "structural-native-distribution-e2e.v85" in e2e
    assert "exercise_model_ir_linear_reaction_view_surface" in e2e
    assert "reaction-view" in e2e
    assert "model_ir_linear_reaction_view_surface_passed" in e2e
    assert "model_ir_linear_reaction_view_restart_parity_passed" in e2e
    assert "model_ir_linear_reaction_view_en_us_sha256" in e2e
    assert "model_ir_linear_reaction_view_ko_kr_sha256" in e2e
    assert "model_ir_linear_reaction_view_window_sha256" in e2e
    assert "mgt_model_ir_linear_reaction_view_surface_passed" in e2e
    assert "mgt_model_ir_linear_reaction_view_restart_parity_passed" in e2e
    assert "mgt_model_ir_linear_reaction_view_en_us_sha256" in e2e
    assert "mgt_model_ir_linear_reaction_view_ko_kr_sha256" in e2e
    assert "workbench_reaction_view_wrong_profile_rejected" in e2e
    assert "structural-native-distribution-e2e.v86" in e2e
    assert "exercise_model_ir_linear_reaction_audit_surface" in e2e
    assert "reaction-audit" in e2e
    assert "model_ir_linear_reaction_audit_surface_passed" in e2e
    assert "model_ir_linear_reaction_audit_restart_parity_passed" in e2e
    assert "model_ir_linear_reaction_audit_en_us_sha256" in e2e
    assert "model_ir_linear_reaction_audit_ko_kr_sha256" in e2e
    assert "mgt_model_ir_linear_reaction_audit_surface_passed" in e2e
    assert "mgt_model_ir_linear_reaction_audit_restart_parity_passed" in e2e
    assert "mgt_model_ir_linear_reaction_audit_en_us_sha256" in e2e
    assert "mgt_model_ir_linear_reaction_audit_ko_kr_sha256" in e2e
    assert "workbench_reaction_audit_wrong_profile_rejected" in e2e
    assert "structural-native-distribution-e2e.v87" in e2e
    assert "exercise_model_ir_linear_nodal_displacement_view_surface" in e2e
    assert "nodal-displacement-view" in e2e
    assert "model_ir_linear_nodal_displacement_view_surface_passed" in e2e
    assert "model_ir_linear_nodal_displacement_view_restart_parity_passed" in e2e
    assert "model_ir_linear_nodal_displacement_view_en_us_sha256" in e2e
    assert "model_ir_linear_nodal_displacement_view_ko_kr_sha256" in e2e
    assert "model_ir_linear_nodal_displacement_view_window_sha256" in e2e
    assert "mgt_model_ir_linear_nodal_displacement_view_surface_passed" in e2e
    assert "mgt_model_ir_linear_nodal_displacement_view_restart_parity_passed" in e2e
    assert "mgt_model_ir_linear_nodal_displacement_view_en_us_sha256" in e2e
    assert "mgt_model_ir_linear_nodal_displacement_view_ko_kr_sha256" in e2e
    assert "workbench_nodal_displacement_view_wrong_profile_rejected" in e2e
    assert "structural-native-distribution-e2e.v88" in e2e
    assert "exercise_model_ir_linear_deformed_view_surface" in e2e
    assert "model_ir_linear_deformed_view_surface_passed" in e2e
    assert "model_ir_linear_deformed_view_restart_parity_passed" in e2e
    assert "model_ir_linear_deformed_view_en_us_sha256" in e2e
    assert "model_ir_linear_deformed_view_ko_kr_sha256" in e2e
    assert "model_ir_linear_deformed_view_projection_sha256" in e2e
    assert "mgt_model_ir_linear_deformed_view_surface_passed" in e2e
    assert "mgt_model_ir_linear_deformed_view_restart_parity_passed" in e2e
    assert "mgt_model_ir_linear_deformed_view_en_us_sha256" in e2e
    assert "mgt_model_ir_linear_deformed_view_ko_kr_sha256" in e2e
    assert "workbench_linear_deformed_view_invalid_step_rejected" in e2e
    assert "structural-native-distribution-e2e.v89" in e2e
    assert "exercise_model_ir_linear_element_recovery_view_surface" in e2e
    assert "model_ir_linear_element_recovery_view_surface_passed" in e2e
    assert "model_ir_linear_element_recovery_view_restart_parity_passed" in e2e
    assert "model_ir_linear_element_recovery_view_en_us_sha256" in e2e
    assert "model_ir_linear_element_recovery_view_ko_kr_sha256" in e2e
    assert "mgt_model_ir_linear_element_recovery_view_surface_passed" in e2e
    assert "mgt_model_ir_linear_element_recovery_view_restart_parity_passed" in e2e
    assert "mgt_model_ir_linear_element_recovery_view_en_us_sha256" in e2e
    assert "mgt_model_ir_linear_element_recovery_view_ko_kr_sha256" in e2e
    assert "workbench_linear_element_recovery_view_invalid_window_rejected" in e2e
    assert "structural-native-distribution-e2e.v90" in e2e
    assert "structural-native-distribution-e2e.v91" in e2e
    assert "structural-native-distribution-e2e.v95" in e2e
    assert "model_ir_self_weight_standard_gravity_passed" in e2e
    assert "model_ir_self_weight_reaction_sha256" in e2e
    assert "structural-native-distribution-e2e.v96" in e2e
    assert "model_ir_frame3d_member_distributed_load_fixed_end_force_passed" in e2e
    assert "model_ir_frame3d_member_distributed_load_reaction_sha256" in e2e
    assert "structural-native-distribution-e2e.v97" in e2e
    assert "model-edit-constraint-value" in e2e
    assert "COMBO_PRESCRIBED" in e2e
    assert "model_ir_frame3d_prescribed_support_effective_rhs_passed" in e2e
    assert "model_ir_frame3d_prescribed_support_reaction_sha256" in e2e
    assert "structural-native-distribution-e2e.v98" in e2e
    assert "structural-native-distribution-e2e.v99" in e2e
    assert "exercise_model_ir_buckling_installed_surface" in e2e
    assert "model-create-buckling-analysis-request" in e2e
    assert "model-buckling-run" in e2e
    assert "model-buckling-resume" in e2e
    assert "buckling-result-view" in e2e
    assert "workflow-model-buckling" in e2e
    assert "model_ir_buckling_product_surface_passed" in e2e
    assert "model_ir_buckling_restart_bitwise_passed" in e2e
    assert "workbench_model_buckling_result_view_read_only_passed" in e2e
    assert "workbench_model_buckling_durable_session_tamper_rejected" in e2e
    assert "submit-model-buckling" in e2e
    assert "model_ir_buckling_durable_job_exact_product_parity_passed" in e2e
    assert "model_ir_buckling_http_named_artifact_parity_passed" in e2e
    assert "exercise_model_ir_modal_installed_surface" in e2e
    assert "model-create-modal-analysis-request" in e2e
    assert "model-modal-run" in e2e
    assert "workbench_model_modal_request_create_surface_passed" in e2e
    assert "model_ir_modal_product_surface_passed" in e2e
    assert "model_ir_modal_repeat_bitwise_passed" in e2e
    assert "workbench_model_modal_unsupported_planar_rejected" in e2e
    assert "model_ir_modal_result_ir_sha256" in e2e
    assert "model_ir_modal_run_receipt_sha256" in e2e
    assert "model-modal-resume" in e2e
    assert "modal-result-view" in e2e
    assert "model_ir_modal_restart_bitwise_passed" in e2e
    assert "workbench_model_modal_result_view_read_only_passed" in e2e
    assert "workbench_fixed_constraint_identity_cascade_edit_restart_passed" in e2e
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
    assert (
        "structural-native-model-ir-linear-engineering-localized-pdf-report-receipt.v3"
        in e2e
    )
    assert "structural-native-sparse-linear-pdf-report-receipt.v1" in e2e
    assert (
        'linear_source_artifact="$frame3d_quickstart_share/'
        'language-neutral-oracle.txt"' in e2e
    )
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
    assert "reaction-view" in rootfs_e2e
    assert "--model-ir-linear-workbench-session-before-reaction-view" in rootfs_e2e
    assert "--mgt-model-ir-linear-workbench-session-before-reaction-view" in rootfs_e2e
    assert "--model-ir-linear-reaction-view-en-us-first" in rootfs_e2e
    assert "--model-ir-linear-reaction-view-window" in rootfs_e2e
    assert "--mgt-model-ir-linear-reaction-view-ko-kr-second" in rootfs_e2e
    assert "--workbench-reaction-view-wrong-profile-failure" in rootfs_e2e
    assert "reaction-audit" in rootfs_e2e
    assert "--model-ir-linear-reaction-audit-en-us-first" in rootfs_e2e
    assert "--model-ir-linear-reaction-audit-ko-kr-second" in rootfs_e2e
    assert "--mgt-model-ir-linear-reaction-audit-en-us-first" in rootfs_e2e
    assert "--mgt-model-ir-linear-reaction-audit-ko-kr-second" in rootfs_e2e
    assert "--workbench-reaction-audit-wrong-profile-failure" in rootfs_e2e
    assert "nodal-displacement-view" in rootfs_e2e
    assert "--model-ir-linear-nodal-displacement-view-en-us-first" in rootfs_e2e
    assert "--model-ir-linear-nodal-displacement-view-window" in rootfs_e2e
    assert "--mgt-model-ir-linear-nodal-displacement-view-en-us-first" in rootfs_e2e
    assert "--mgt-model-ir-linear-nodal-displacement-view-ko-kr-second" in rootfs_e2e
    assert "--workbench-nodal-displacement-view-wrong-profile-failure" in rootfs_e2e
    assert "result-deformed-view" in rootfs_e2e
    assert "--model-ir-linear-deformed-view-en-us-first" in rootfs_e2e
    assert "--model-ir-linear-deformed-view-projection" in rootfs_e2e
    assert "--mgt-model-ir-linear-deformed-view-en-us-first" in rootfs_e2e
    assert "--mgt-model-ir-linear-deformed-view-ko-kr-second" in rootfs_e2e
    assert "--workbench-linear-deformed-view-invalid-step-failure" in rootfs_e2e
    assert "element-recovery-view" in rootfs_e2e
    assert "--model-ir-linear-element-recovery-view-en-us-first" in rootfs_e2e
    assert "--model-ir-linear-element-recovery-view-ko-kr-second" in rootfs_e2e
    assert "--mgt-model-ir-linear-element-recovery-view-en-us-first" in rootfs_e2e
    assert "--mgt-model-ir-linear-element-recovery-view-ko-kr-second" in rootfs_e2e
    assert (
        "--workbench-linear-element-recovery-view-invalid-window-failure" in rootfs_e2e
    )
    assert "model-create-modal-analysis-request" in rootfs_e2e
    assert "model-modal-run" in rootfs_e2e
    assert "model-modal-resume" in rootfs_e2e
    assert "modal-result-view" in rootfs_e2e
    assert "--model-modal-direct-root" in rootfs_e2e
    assert "--model-modal-resumed-root" in rootfs_e2e
    assert "--model-modal-result-view-en-us-first" in rootfs_e2e
    assert "--model-modal-result-view-invalid-window-failure" in rootfs_e2e
    assert "frame3d-self-weight-model-ir.json" in rootfs_e2e
    assert "--frame3d-self-weight-model" in rootfs_e2e
    assert "--frame3d-self-weight-resumed-root" in rootfs_e2e
    assert "frame3d-prescribed-support-model-ir.json" in rootfs_e2e
    assert "model-edit-constraint-value" in rootfs_e2e
    assert "COMBO_PRESCRIBED" in rootfs_e2e
    assert "--frame3d-prescribed-support-model" in rootfs_e2e
    assert "--frame3d-prescribed-support-edit-root" in rootfs_e2e
    assert "--frame3d-prescribed-support-combination-root" in rootfs_e2e
    assert "--frame3d-prescribed-support-resumed-root" in rootfs_e2e
    assert "model-create-buckling-analysis-request" in rootfs_e2e
    assert "model-buckling-run" in rootfs_e2e
    assert "model-buckling-resume" in rootfs_e2e
    assert "buckling-result-view" in rootfs_e2e
    assert "workflow-model-buckling" in rootfs_e2e
    assert "buckling-inspect" in rootfs_e2e
    assert "--model-buckling-direct-root" in rootfs_e2e
    assert "--model-buckling-resumed-root" in rootfs_e2e
    assert "--model-buckling-result-view-en-us-first" in rootfs_e2e
    assert "--model-buckling-result-view-invalid-window-failure" in rootfs_e2e
    assert "--model-buckling-workbench-restarted-root" in rootfs_e2e
    assert "--model-buckling-workbench-reconciled-stdout" in rootfs_e2e
    assert "--model-buckling-workbench-tamper-failure" in rootfs_e2e
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
    assert "exercise_orphan_node_delete_surface" in e2e
    assert "model-delete-orphan-node" in e2e
    assert "workbench_orphan_node_delete_surface_passed" in e2e
    assert "workbench_orphan_node_delete_model_sha256" in e2e
    assert "workbench_orphan_node_delete_receipt_sha256" in e2e
    assert "workbench_orphan_node_delete_request_sha256" in e2e
    assert "workbench_orphan_node_delete_result_ir_sha256" in e2e
    assert "workbench_orphan_node_delete_recovery_sha256" in e2e
    assert "exercise_linear_load_combination_add_surface" in e2e
    assert "model-add-linear-load-combination" in e2e
    assert "workbench_linear_load_combination_add_surface_passed" in e2e
    assert "workbench_linear_load_combination_add_model_sha256" in e2e
    assert "workbench_linear_load_combination_add_receipt_sha256" in e2e
    assert "workbench_linear_load_combination_add_validation_sha256" in e2e
    assert "workbench_linear_load_combination_add_view_sha256" in e2e
    assert "workbench_linear_load_combination_add_solver_rejection_sha256" in e2e
    assert "--load-combination COMBO_SERVICE" in e2e
    assert "structural-native-model-linear-combination-request-create-receipt.v1" in e2e
    assert "workbench_linear_load_combination_execution_surface_passed" in e2e
    assert "workbench_linear_load_combination_request_receipt_sha256" in e2e
    assert "workbench_linear_load_combination_request_sha256" in e2e
    assert "workbench_linear_load_combination_assembly_receipt_sha256" in e2e
    assert "workbench_linear_load_combination_checkpoint_sha256" in e2e
    assert "workbench_linear_load_combination_result_ir_sha256" in e2e
    assert "workbench_linear_load_combination_recovery_sha256" in e2e
    assert "workbench_linear_load_combination_report_ir_sha256" in e2e
    assert "workbench_linear_load_combination_restart_passed" in e2e
    assert "exercise_direct_linear_load_combination_surface" in e2e
    assert (
        "structural-native-model-linear-direct-combination-request-create-receipt.v2"
        in e2e
    )
    assert "workbench_direct_linear_load_combination_surface_passed" in e2e
    assert "workbench_direct_linear_load_combination_model_sha256" in e2e
    assert "workbench_direct_linear_load_combination_edit_receipt_sha256" in e2e
    assert "workbench_direct_linear_load_combination_request_receipt_sha256" in e2e
    assert "workbench_direct_linear_load_combination_request_sha256" in e2e
    assert "workbench_direct_linear_load_combination_assembly_receipt_sha256" in e2e
    assert "workbench_direct_linear_load_combination_checkpoint_sha256" in e2e
    assert "workbench_direct_linear_load_combination_result_ir_sha256" in e2e
    assert "workbench_direct_linear_load_combination_recovery_sha256" in e2e
    assert "workbench_direct_linear_load_combination_report_ir_sha256" in e2e
    assert "workbench_direct_linear_load_combination_restart_passed" in e2e
    assert "exercise_nested_linear_load_combination_surface" in e2e
    assert "model-add-nested-linear-load-combination" in e2e
    assert (
        "structural-native-model-linear-nested-combination-request-create-receipt.v3"
        in e2e
    )
    assert "workbench_nested_linear_load_combination_surface_passed" in e2e
    assert "workbench_nested_linear_load_combination_model_sha256" in e2e
    assert "workbench_nested_linear_load_combination_edit_receipt_sha256" in e2e
    assert "workbench_nested_linear_load_combination_request_receipt_sha256" in e2e
    assert "workbench_nested_linear_load_combination_request_sha256" in e2e
    assert "workbench_nested_linear_load_combination_assembly_receipt_sha256" in e2e
    assert "workbench_nested_linear_load_combination_checkpoint_sha256" in e2e
    assert "workbench_nested_linear_load_combination_result_ir_sha256" in e2e
    assert "workbench_nested_linear_load_combination_recovery_sha256" in e2e
    assert "workbench_nested_linear_load_combination_report_ir_sha256" in e2e
    assert "workbench_nested_linear_load_combination_restart_passed" in e2e
    assert "exercise_direct_linear_load_combination_delete_surface" in e2e
    assert "structural-native:model-delete-direct-linear-load-combination.v2" in e2e
    assert "workbench_direct_linear_load_combination_delete_surface_passed" in e2e
    assert "workbench_direct_linear_load_combination_delete_model_sha256" in e2e
    assert "workbench_direct_linear_load_combination_delete_receipt_sha256" in e2e
    assert "workbench_direct_linear_load_combination_delete_request_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_delete_assembly_receipt_sha256" in e2e
    )
    assert "workbench_direct_linear_load_combination_delete_checkpoint_sha256" in e2e
    assert "workbench_direct_linear_load_combination_delete_result_ir_sha256" in e2e
    assert "workbench_direct_linear_load_combination_delete_recovery_sha256" in e2e
    assert "workbench_direct_linear_load_combination_delete_report_ir_sha256" in e2e
    assert "workbench_direct_linear_load_combination_delete_restart_passed" in e2e
    assert "exercise_nested_linear_load_combination_delete_surface" in e2e
    assert "structural-native:model-delete-nested-linear-load-combination.v3" in e2e
    assert "workbench_nested_linear_load_combination_delete_surface_passed" in e2e
    assert "workbench_nested_linear_load_combination_delete_model_sha256" in e2e
    assert "workbench_nested_linear_load_combination_delete_receipt_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_delete_request_receipt_sha256" in e2e
    )
    assert "workbench_nested_linear_load_combination_delete_request_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_delete_assembly_receipt_sha256" in e2e
    )
    assert "workbench_nested_linear_load_combination_delete_checkpoint_sha256" in e2e
    assert "workbench_nested_linear_load_combination_delete_result_ir_sha256" in e2e
    assert "workbench_nested_linear_load_combination_delete_recovery_sha256" in e2e
    assert "workbench_nested_linear_load_combination_delete_report_ir_sha256" in e2e
    assert "workbench_nested_linear_load_combination_delete_restart_passed" in e2e
    assert "exercise_direct_linear_load_combination_factor_edit_surface" in e2e
    assert "model-edit-linear-load-combination-factor" in e2e
    assert (
        "structural-native:model-edit-direct-linear-load-combination-factor.v1" in e2e
    )
    assert "workbench_direct_linear_load_combination_factor_edit_surface_passed" in e2e
    assert "workbench_direct_linear_load_combination_factor_edit_model_sha256" in e2e
    assert "workbench_direct_linear_load_combination_factor_edit_receipt_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_factor_edit_request_receipt_sha256"
        in e2e
    )
    assert "workbench_direct_linear_load_combination_factor_edit_request_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_factor_edit_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_factor_edit_checkpoint_sha256" in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_factor_edit_result_ir_sha256" in e2e
    )
    assert "workbench_direct_linear_load_combination_factor_edit_recovery_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_factor_edit_report_ir_sha256" in e2e
    )
    assert "workbench_direct_linear_load_combination_factor_edit_restart_passed" in e2e
    assert "exercise_nested_linear_load_combination_factor_edit_surface" in e2e
    assert "model-edit-nested-linear-load-combination-factor" in e2e
    assert (
        "structural-native:model-edit-nested-linear-load-combination-factor.v1" in e2e
    )
    assert "workbench_nested_linear_load_combination_factor_edit_surface_passed" in e2e
    assert "workbench_nested_linear_load_combination_factor_edit_model_sha256" in e2e
    assert "workbench_nested_linear_load_combination_factor_edit_receipt_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_factor_edit_request_receipt_sha256"
        in e2e
    )
    assert "workbench_nested_linear_load_combination_factor_edit_request_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_factor_edit_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_factor_edit_checkpoint_sha256" in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_factor_edit_result_ir_sha256" in e2e
    )
    assert "workbench_nested_linear_load_combination_factor_edit_recovery_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_factor_edit_report_ir_sha256" in e2e
    )
    assert "workbench_nested_linear_load_combination_factor_edit_restart_passed" in e2e
    assert "exercise_direct_linear_load_combination_reference_edit_surface" in e2e
    assert "model-edit-linear-load-combination-reference" in e2e
    assert (
        "structural-native:model-edit-direct-linear-load-combination-reference.v1"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_reference_edit_surface_passed" in e2e
    )
    assert "workbench_direct_linear_load_combination_reference_edit_model_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_reference_edit_receipt_sha256" in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_reference_edit_request_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_reference_edit_request_sha256" in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_reference_edit_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_reference_edit_checkpoint_sha256"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_reference_edit_result_ir_sha256"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_reference_edit_recovery_sha256" in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_reference_edit_report_ir_sha256"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_reference_edit_restart_passed" in e2e
    )
    assert "exercise_nested_linear_load_combination_reference_edit_surface" in e2e
    assert "model-edit-nested-linear-load-combination-reference" in e2e
    assert (
        "structural-native:model-edit-nested-linear-load-combination-reference.v1"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_reference_edit_surface_passed" in e2e
    )
    assert "workbench_nested_linear_load_combination_reference_edit_model_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_reference_edit_receipt_sha256" in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_reference_edit_request_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_reference_edit_request_sha256" in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_reference_edit_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_reference_edit_checkpoint_sha256"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_reference_edit_result_ir_sha256"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_reference_edit_recovery_sha256" in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_reference_edit_report_ir_sha256"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_reference_edit_restart_passed" in e2e
    )
    assert "exercise_direct_linear_load_combination_term_add_surface" in e2e
    assert "model-add-linear-load-combination-term" in e2e
    assert "structural-native:model-add-direct-linear-load-combination-term.v1" in e2e
    assert "workbench_direct_linear_load_combination_term_add_surface_passed" in e2e
    assert "workbench_direct_linear_load_combination_term_add_model_sha256" in e2e
    assert "workbench_direct_linear_load_combination_term_add_receipt_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_add_request_receipt_sha256"
        in e2e
    )
    assert "workbench_direct_linear_load_combination_term_add_request_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_add_assembly_receipt_sha256"
        in e2e
    )
    assert "workbench_direct_linear_load_combination_term_add_checkpoint_sha256" in e2e
    assert "workbench_direct_linear_load_combination_term_add_result_ir_sha256" in e2e
    assert "workbench_direct_linear_load_combination_term_add_recovery_sha256" in e2e
    assert "workbench_direct_linear_load_combination_term_add_report_ir_sha256" in e2e
    assert "workbench_direct_linear_load_combination_term_add_restart_passed" in e2e
    assert "exercise_direct_linear_load_combination_term_delete_surface" in e2e
    assert "model-delete-linear-load-combination-term" in e2e
    assert (
        "structural-native:model-delete-direct-linear-load-combination-term.v1" in e2e
    )
    assert "workbench_direct_linear_load_combination_term_delete_surface_passed" in e2e
    assert "workbench_direct_linear_load_combination_term_delete_model_sha256" in e2e
    assert "workbench_direct_linear_load_combination_term_delete_receipt_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_delete_request_receipt_sha256"
        in e2e
    )
    assert "workbench_direct_linear_load_combination_term_delete_request_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_delete_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_term_delete_checkpoint_sha256" in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_term_delete_result_ir_sha256" in e2e
    )
    assert "workbench_direct_linear_load_combination_term_delete_recovery_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_delete_report_ir_sha256" in e2e
    )
    assert "workbench_direct_linear_load_combination_term_delete_restart_passed" in e2e
    assert "exercise_direct_linear_load_combination_term_reorder_surface" in e2e
    assert "model-reorder-linear-load-combination-term" in e2e
    assert (
        "structural-native:model-reorder-direct-linear-load-combination-term.v1" in e2e
    )
    assert "workbench_direct_linear_load_combination_term_reorder_surface_passed" in e2e
    assert "workbench_direct_linear_load_combination_term_reorder_model_sha256" in e2e
    assert "workbench_direct_linear_load_combination_term_reorder_receipt_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_reorder_request_receipt_sha256"
        in e2e
    )
    assert "workbench_direct_linear_load_combination_term_reorder_request_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_reorder_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_term_reorder_checkpoint_sha256" in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_term_reorder_result_ir_sha256" in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_term_reorder_recovery_sha256" in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_term_reorder_report_ir_sha256" in e2e
    )
    assert "workbench_direct_linear_load_combination_term_reorder_restart_passed" in e2e
    assert "exercise_direct_linear_load_combination_term_insert_surface" in e2e
    assert "model-insert-linear-load-combination-term" in e2e
    assert (
        "structural-native:model-insert-direct-linear-load-combination-term.v1" in e2e
    )
    assert "workbench_direct_linear_load_combination_term_insert_surface_passed" in e2e
    assert "workbench_direct_linear_load_combination_term_insert_model_sha256" in e2e
    assert "workbench_direct_linear_load_combination_term_insert_receipt_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_insert_request_receipt_sha256"
        in e2e
    )
    assert "workbench_direct_linear_load_combination_term_insert_request_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_insert_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_term_insert_checkpoint_sha256" in e2e
    )
    assert (
        "workbench_direct_linear_load_combination_term_insert_result_ir_sha256" in e2e
    )
    assert "workbench_direct_linear_load_combination_term_insert_recovery_sha256" in e2e
    assert (
        "workbench_direct_linear_load_combination_term_insert_report_ir_sha256" in e2e
    )
    assert "workbench_direct_linear_load_combination_term_insert_restart_passed" in e2e
    assert "exercise_nested_linear_load_combination_term_insert_surface" in e2e
    assert "model-insert-nested-linear-load-combination-term" in e2e
    assert (
        "structural-native:model-insert-nested-linear-load-combination-term.v1" in e2e
    )
    assert "workbench_nested_linear_load_combination_term_insert_surface_passed" in e2e
    assert "workbench_nested_linear_load_combination_term_insert_model_sha256" in e2e
    assert "workbench_nested_linear_load_combination_term_insert_receipt_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_insert_request_receipt_sha256"
        in e2e
    )
    assert "workbench_nested_linear_load_combination_term_insert_request_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_insert_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_term_insert_checkpoint_sha256" in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_term_insert_result_ir_sha256" in e2e
    )
    assert "workbench_nested_linear_load_combination_term_insert_recovery_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_insert_report_ir_sha256" in e2e
    )
    assert "workbench_nested_linear_load_combination_term_insert_restart_passed" in e2e
    assert "exercise_nested_linear_load_combination_term_add_surface" in e2e
    assert "model-add-nested-linear-load-combination-term" in e2e
    assert "structural-native:model-add-nested-linear-load-combination-term.v1" in e2e
    assert "workbench_nested_linear_load_combination_term_add_surface_passed" in e2e
    assert "workbench_nested_linear_load_combination_term_add_model_sha256" in e2e
    assert "workbench_nested_linear_load_combination_term_add_receipt_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_add_request_receipt_sha256"
        in e2e
    )
    assert "workbench_nested_linear_load_combination_term_add_request_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_add_assembly_receipt_sha256"
        in e2e
    )
    assert "workbench_nested_linear_load_combination_term_add_checkpoint_sha256" in e2e
    assert "workbench_nested_linear_load_combination_term_add_result_ir_sha256" in e2e
    assert "workbench_nested_linear_load_combination_term_add_recovery_sha256" in e2e
    assert "workbench_nested_linear_load_combination_term_add_report_ir_sha256" in e2e
    assert "workbench_nested_linear_load_combination_term_add_restart_passed" in e2e
    assert "exercise_nested_linear_load_combination_term_delete_surface" in e2e
    assert "model-delete-nested-linear-load-combination-term" in e2e
    assert (
        "structural-native:model-delete-nested-linear-load-combination-term.v1" in e2e
    )
    assert "workbench_nested_linear_load_combination_term_delete_surface_passed" in e2e
    assert "workbench_nested_linear_load_combination_term_delete_model_sha256" in e2e
    assert "workbench_nested_linear_load_combination_term_delete_receipt_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_delete_request_receipt_sha256"
        in e2e
    )
    assert "workbench_nested_linear_load_combination_term_delete_request_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_delete_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_term_delete_checkpoint_sha256" in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_term_delete_result_ir_sha256" in e2e
    )
    assert "workbench_nested_linear_load_combination_term_delete_recovery_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_delete_report_ir_sha256" in e2e
    )
    assert "workbench_nested_linear_load_combination_term_delete_restart_passed" in e2e
    assert "exercise_nested_linear_load_combination_term_reorder_surface" in e2e
    assert "model-reorder-nested-linear-load-combination-term" in e2e
    assert (
        "structural-native:model-reorder-nested-linear-load-combination-term.v1" in e2e
    )
    assert "workbench_nested_linear_load_combination_term_reorder_surface_passed" in e2e
    assert "workbench_nested_linear_load_combination_term_reorder_model_sha256" in e2e
    assert "workbench_nested_linear_load_combination_term_reorder_receipt_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_reorder_request_receipt_sha256"
        in e2e
    )
    assert "workbench_nested_linear_load_combination_term_reorder_request_sha256" in e2e
    assert (
        "workbench_nested_linear_load_combination_term_reorder_assembly_receipt_sha256"
        in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_term_reorder_checkpoint_sha256" in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_term_reorder_result_ir_sha256" in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_term_reorder_recovery_sha256" in e2e
    )
    assert (
        "workbench_nested_linear_load_combination_term_reorder_report_ir_sha256" in e2e
    )
    assert "workbench_nested_linear_load_combination_term_reorder_restart_passed" in e2e
    assert "exercise_linear_load_combination_delete_surface" in e2e
    assert "model-delete-linear-load-combination" in e2e
    assert "workbench_linear_load_combination_delete_surface_passed" in e2e
    assert "workbench_linear_load_combination_delete_model_sha256" in e2e
    assert "workbench_linear_load_combination_delete_receipt_sha256" in e2e
    assert "workbench_linear_load_combination_delete_request_sha256" in e2e
    assert "workbench_linear_load_combination_delete_result_ir_sha256" in e2e
    assert "workbench_linear_load_combination_delete_recovery_sha256" in e2e
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
    assert 'structural_native_backend_package_consumer" hip' in rocm_e2e
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
    assert '"approved_device_runner\\":true' in rocm_e2e
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
