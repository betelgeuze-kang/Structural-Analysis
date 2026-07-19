from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/build_g1_mgt_matrix_free_preconditioner_candidate_audit.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_matrix_free_preconditioner_candidate_audit",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _committed_receipt() -> dict:
    return module._read_json(ROOT / module.DEFAULT_RECEIPT_OUT)


def test_committed_receipt_records_block_jacobi_counterevidence() -> None:
    payload = _committed_receipt()

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["diagnostic_execution_ready"] is True
    assert payload["readiness_pass"] is False
    assert payload["evidence_closure_pass"] is False
    assert payload["inputs"]["equation_count"] == 70_560
    assert payload["inputs"]["load_factor"] == 1.0
    assert payload["inputs"]["right_hand_side_inf_kn"] == pytest.approx(
        3.8238140951064206
    )

    binding = payload["operator_binding"]
    assert binding["status"] == "ready"
    assert binding["free_equation_order_data_hash"] == (
        "sha256:21e0cef7915f3c68a772ca541123453a"
        "35535c3b172110ebd54f16695541c1b1"
    )
    assert binding["residual_formula_hash"] == (
        "sha256:2da9d3377eaf3cd9b196e82535c3a3593502079652306bc5705e13d910cca62f"
    )
    assert binding["current_tangent_operator_profile"] == (
        "reference_csr_load_frame_delta_finite_chord_axial.v1"
    )
    assert binding["current_tangent_operator_contract_hash"] == (
        "sha256:56fdb87292249c79557198159590710394f0b0482acf5552d55d7888cd730177"
    )
    assert binding["current_tangent_operator_array_bundle_hash"] == (
        "sha256:19b833d0334ed923586aa9797459fec2814f138d1d7cf525d4f62ea9267a9118"
    )
    assert binding["operator_callback_reference_evaluator"] == (
        "numpy_fp64_array_formula_reference.v1"
    )
    assert binding["operator_callback_outputs_in_contract"] is True

    current_tangent = payload["current_tangent_operator_contract"]
    manifest = current_tangent["manifest"]
    assert module.validate_current_tangent_operator_manifest(manifest)
    assert manifest["contract_hash"] == binding[
        "current_tangent_operator_contract_hash"
    ]
    assert manifest["array_bundle_hash"] == binding[
        "current_tangent_operator_array_bundle_hash"
    ]
    assert manifest["dimensions"] == {
        "equation_count": 70_560,
        "frame_element_count": 5_572,
        "geometry_element_count": 5_572,
        "global_dof_count": 78_282,
        "reference_nnz": 1_262_462,
    }
    assert len(manifest["array_descriptors"]) == 12
    assert [row["name"] for row in manifest["array_descriptors"]] == [
        "reference_row_pointer",
        "reference_column_indices",
        "reference_values_n_per_m",
        "free_global_dofs",
        "background_global_displacements_m",
        "frame_dofs",
        "frame_stiffness_delta_n_per_m",
        "geometry_dofs",
        "geometry_relative_translation_operators",
        "geometry_reference_chords_m",
        "geometry_reference_lengths_m",
        "geometry_axial_stiffness_n_per_m",
    ]
    assert current_tangent["array_total_byte_length"] == 31_271_000
    assert current_tangent[
        "reference_preconditioner_pattern_hash"
    ] == "sha256:0e87f2fd7d981ea5b16b472f843775fa8a7204bcbfab999f40c98c27353f0423"
    assert current_tangent[
        "reference_preconditioner_numeric_values_hash"
    ] == "sha256:e8acc6e11594cdf375d8972c8c3292e97c5ada72e250a07273fa5fe1a636f4e1"
    probes = current_tangent["analytic_callback_parity_probes"]
    assert [row["probe"] for row in probes] == [
        "normalized_full_unit_predictor",
        "normalized_current_right_hand_side",
    ]
    assert all(row["gate_passed"] for row in probes)
    assert all(
        row["relative_difference"] <= row["relative_tolerance"]
        for row in probes
    )
    assert probes[0]["difference_inf_n_per_m"] == pytest.approx(
        0.0003086477518081665
    )
    assert probes[0]["relative_difference"] == pytest.approx(
        4.480068989692911e-12
    )
    assert probes[1]["difference_inf_n_per_m"] == pytest.approx(0.25)
    assert probes[1]["relative_difference"] == pytest.approx(
        1.8032488261425373e-16
    )
    assert all(row["action_bytes_exact"] is False for row in probes)
    assert current_tangent["analytic_callback_parity_pass"] is True
    assert current_tangent["operator_callback_outputs_in_contract"] is True
    assert current_tangent["cpu_reference_evaluator_executed"] is True
    assert current_tangent["hip_execution"] is True
    assert current_tangent["cpu_hip_numerical_parity"] is True
    assert current_tangent["contract_pass"] is True

    hip_current_tangent = payload[
        "hip_current_tangent_execution_preparation"
    ]
    compile_evidence = hip_current_tangent["compile_evidence"]
    assert compile_evidence["schema_version"] == (
        "engine-v2-hip-current-tangent-target-compile-host-parse-receipt.v1"
    )
    assert compile_evidence["contract_scope"] == (
        "target_compile_and_host_fixture_parser_only"
    )
    assert compile_evidence["compiler"]["version_first_line"] == (
        "HIP version: 6.0.32831-204d35d16"
    )
    assert compile_evidence["host_parser_fixture_scope"] == (
        "five_equation_synthetic_fixture_only"
    )
    assert [
        row["architecture"] for row in compile_evidence["targets"]
    ] == ["gfx1030", "gfx1100"]
    assert [
        (row["binary_byte_length"], row["binary_sha256"])
        for row in compile_evidence["targets"]
    ] == [
        (
            56_912,
            "sha256:2b579ec5b651a5c7503318a9fe59efcf688d1690726f8bb3e51662de942e39d4",
        ),
        (
            57_680,
            "sha256:2c99d9a6e65118185b783e5151af5480e17a86cb38dac907195d67a3e421b654",
        ),
    ]
    assert all(
        row["target_compile"] is True
        and row["host_fixture_parser_execution"] is True
        and row["host_fixture_validation"]["equation_count"] == 5
        and row["host_fixture_validation"]["fixture_byte_length"] == 2_600
        and row["host_fixture_validation"]["actual_hardware_execution"]
        is False
        and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
        for row in compile_evidence["targets"]
    )
    assert compile_evidence["dual_target_compile_pass"] is True
    assert compile_evidence[
        "dual_target_host_fixture_parser_execution"
    ] is True

    actual_host_parser = hip_current_tangent[
        "actual_mgt_host_parser_receipt"
    ]
    assert actual_host_parser["schema_version"] == (
        "g1-mgt-hip-current-tangent-host-parser-receipt.v1"
    )
    assert actual_host_parser["contract_scope"] == (
        "actual_mgt_dual_target_compile_and_host_fixture_parser_only"
    )
    assert actual_host_parser[
        "synthetic_and_actual_parser_binary_identity"
    ] is True
    assert actual_host_parser[
        "dual_target_host_fixture_parser_execution"
    ] is True
    assert actual_host_parser["hip_runtime_api_call_count"] == 0
    assert actual_host_parser["actual_hardware_execution"] is False
    assert actual_host_parser["current_tangent_action_executed"] is False
    assert actual_host_parser["cpu_hip_numerical_parity"] is False
    assert actual_host_parser["contract_pass"] is True
    assert [row["architecture"] for row in actual_host_parser["targets"]] == [
        "gfx1030",
        "gfx1100",
    ]
    assert all(
        row["host_fixture_parser_execution"] is True
        and row["host_fixture_validation"]["equation_count"] == 70_560
        and row["host_fixture_validation"]["fixture_byte_length"]
        == 36_123_072
        and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
        for row in actual_host_parser["targets"]
    )

    actual_hardware = hip_current_tangent[
        "actual_mgt_hardware_parity_receipt"
    ]
    assert actual_hardware["schema_version"] == (
        "g1-mgt-hip-current-tangent-hardware-parity-receipt.v1"
    )
    assert actual_hardware["contract_scope"] == (
        "actual_mgt_single_state_direction_local_gfx1030_hardware_parity"
    )
    assert actual_hardware["device_name"] == "AMD Radeon RX 6900 XT"
    assert actual_hardware["gcn_arch_name"] == "gfx1030"
    assert actual_hardware["binary_byte_length"] == 56_912
    assert actual_hardware["kernel_invocation_count"] == 1
    assert actual_hardware["mid_action_d2h_transfer_count"] == 0
    assert actual_hardware["blocking_d2h_synchronization_count"] == 1
    assert actual_hardware[
        "canonical_cpu_max_abs_error_n_per_m"
    ] == 0.0625
    assert actual_hardware["device_order_cpu_max_abs_error_n_per_m"] == 0.0
    assert actual_hardware["device_order_bitwise_match"] is True
    assert actual_hardware["action_artifact"]["byte_length"] == 564_480
    assert actual_hardware["action_artifact"]["data_hash"] == (
        "sha256:9c2eb32c3e568252b0b1a5c3b9e2f8176df19f597742fe6d1439b5cb733a97ab"
    )
    assert actual_hardware["actual_hardware_execution"] is True
    assert actual_hardware["cpu_hip_numerical_parity"] is True
    assert actual_hardware["independent_gfx1100_hardware_execution"] is False
    assert actual_hardware["contract_pass"] is True

    actual_fixture = hip_current_tangent["actual_mgt_fixture"]
    assert actual_fixture["fixture_schema_version"] == (
        "engine-v2-hip-current-tangent-operator-fixture.v1"
    )
    assert actual_fixture["parity_profile"] == (
        "engine-v2-cpu-hip-current-tangent-operator-parity.v1"
    )
    assert actual_fixture["schedule_profile"] == (
        "free_row_sorted_element_local_incidence.v1"
    )
    assert actual_fixture["execution_profile"] == (
        "one_thread_per_free_row_reference_frame_geometry.v1"
    )
    assert actual_fixture["accumulation_profile"] == (
        "reference_then_sorted_frame_then_sorted_geometry_sequential_fp64.v1"
    )
    assert actual_fixture["fixture_hash"] == (
        "sha256:e1163543967ed51afb8db7a4fea0a684ef2e115543294f6073ab79a18060115d"
    )
    assert actual_fixture["schedule_contract_hash"] == (
        "sha256:28c279ec2c02123e179509db764536cf5de694c65ece634607e6fdac58313b8b"
    )
    assert actual_fixture["execution_contract_hash"] == (
        "sha256:586adf46e4ab752ce77d4495df657b21632a0646490adaef79e04c786bf5f5c5"
    )
    assert actual_fixture["operator_contract_hash"] == manifest[
        "contract_hash"
    ]
    assert actual_fixture["state_data_hash"] == payload["inputs"][
        "state_data_hash"
    ]
    assert actual_fixture["direction_data_hash"] == (
        "sha256:c240387fb39527236a859f5ea70740e007e445b53c66154c8b2c9ad761824044"
    )
    assert actual_fixture["dimensions"] == {
        "equation_count": 70_560,
        "frame_element_count": 5_572,
        "frame_incidence_count": 61_494,
        "geometry_element_count": 5_572,
        "geometry_incidence_count": 61_494,
        "global_dof_count": 78_282,
        "reference_nnz": 1_262_462,
    }
    assert actual_fixture["expected_kernel_invocation_count"] == 1
    assert actual_fixture["binary_profile"] == (
        "canonical_little_endian_mixed_numeric.v1"
    )
    assert actual_fixture["array_count"] == 21
    assert actual_fixture["fixture_byte_length"] == 36_123_072
    assert actual_fixture["fixture_binary_materialized"] is True
    assert actual_fixture["fixture_binary_ephemeral"] is True
    assert actual_fixture["fixture_binary_sha256"] == actual_fixture[
        "fixture_hash"
    ]
    assert actual_fixture["fixture_binary_readback_sha256"] == (
        actual_fixture["fixture_binary_sha256"]
    )
    assert actual_fixture["fixture_binary_roundtrip_pass"] is True
    assert actual_fixture["fixture_binary_persisted"] is False
    assert actual_fixture["actual_mgt_fixture_contract_pass"] is True
    assert actual_fixture["host_fixture_parser_execution"] is True
    assert actual_fixture["host_fixture_parser_target_count"] == 2
    assert actual_fixture[
        "host_fixture_parser_hip_runtime_api_call_count"
    ] == 0
    assert actual_fixture["host_fixture_parser_binding_pass"] is True
    assert actual_fixture["device_execution"] is True
    assert actual_fixture["cpu_hip_numerical_parity"] is True
    assert hip_current_tangent["actual_hardware_execution"] is True
    assert hip_current_tangent["numerical_parity"] is True
    assert hip_current_tangent[
        "production_current_tangent_fgmres"
    ] is False
    assert hip_current_tangent["performance"] is False
    assert hip_current_tangent["contract_pass"] is True

    recurrence = payload["host_recurrence_contract"]
    assert recurrence["accumulation_profile"] == (
        "ascending_index_python_fsum_fp64.v1"
    )
    assert recurrence["deterministic_host_arithmetic"] is True
    assert recurrence["operator_callback_outputs_in_contract"] is True
    assert recurrence["preconditioner_callback_outputs_in_contract"] is False

    baseline = payload["fixed_reference_splu_baseline"]
    assert baseline["iteration_count"] == 3
    assert baseline["operator_action_count"] == 6
    assert baseline["explicit_residual_inf_kn"] == pytest.approx(
        4.116211867882802e-10
    )
    assert baseline["residual_gate_passed"] is True
    assert baseline["production_preconditioner_claim"] is False

    candidate = payload["node_block_jacobi_candidate"]
    construction = candidate["construction"]
    assert construction["block_count"] == 12_606
    assert construction["singular_block_count"] == 0
    assert construction["inverse_operator_nnz"] == 408_132
    assert construction["fallback_exercised"] is False
    assert construction["deterministic_construction_claim"] is False
    assert candidate["converged"] is False
    assert candidate["terminal_reason"] == "max_iterations"
    assert candidate["iteration_count"] == 120
    assert candidate["restart_count"] == 7
    assert candidate["operator_action_count"] == 129
    assert candidate["preconditioner_application_count"] == 120
    assert candidate["explicit_residual_check_count"] == 9
    assert [
        row["iteration"] for row in candidate["explicit_observations"]
    ] == [0, 15, 30, 45, 60, 75, 90, 105, 120]
    assert candidate["iteration_30_explicit_residual_inf_kn"] == pytest.approx(
        0.0635380270608536
    )
    assert candidate[
        "iteration_120_explicit_residual_inf_kn"
    ] == pytest.approx(0.055947460855883424)
    assert 0.8 < candidate["iteration_30_to_120_residual_ratio"] < 0.9
    assert candidate["final_explicit_residual_inf_kn"] == pytest.approx(
        candidate["independent_residual_inf_kn"]
    )
    assert candidate["residual_gate_kn"] == 5.0e-7
    assert candidate["residual_gate_passed"] is False
    assert candidate["residual_gate_exceedance_factor"] > 100_000
    assert candidate["candidate_counterevidence_pass"] is True
    assert candidate["portable_apply_topology_candidate"] is True
    assert candidate["production_preconditioner_effectiveness_claim"] is False
    assert candidate["hip_apply_parity_claim"] is False
    assert candidate["performance_claim"] is False

    host_ilut = payload["host_ilut_candidate"]
    assert host_ilut["profile"] == (
        "canonical_csr_ilut_fixed_reference_factor.v1"
    )
    construction = host_ilut["construction"]
    assert construction["factorization_backend"] == (
        "scipy.sparse.linalg.spilu_superlu"
    )
    assert construction["drop_tolerance"] == 1.0e-6
    assert construction["fill_factor"] == 20.0
    assert construction["column_permutation"] == "COLAMD"
    assert construction["reference_matrix_nnz"] == 1_262_462
    assert construction["lower_factor"]["nnz"] == 5_975_205
    assert construction["upper_factor"]["nnz"] == 6_579_694
    assert construction["factor_nnz"] == 12_554_899
    assert construction["factor_fill_ratio"] == pytest.approx(
        9.944773783290112
    )
    assert construction["deterministic_construction_claim"] is False
    assert construction[
        "serialized_backend_neutral_factor_artifact_claim"
    ] is True
    manifest = host_ilut["canonical_factor_manifest"]
    assert manifest["profile"] == "canonical_csr_sparse_lu_factor.v1"
    assert manifest["contract_hash"] == construction["factor_contract_hash"]
    assert manifest["dimension"] == 70_560
    assert manifest["lower_nnz"] == construction["lower_factor"]["nnz"]
    assert manifest["upper_nnz"] == construction["upper_factor"]["nnz"]
    assert manifest["factor_nnz"] == construction["factor_nnz"]
    assert manifest["array_count"] == 8
    assert manifest["total_byte_length"] > 100_000_000
    assert manifest["total_byte_length"] == sum(
        row["byte_length"] for row in manifest["arrays"].values()
    )
    assert manifest["apply_contract"]["within_row_accumulation"] == (
        "ascending_column_python_fsum_fp64"
    )
    binary_manifest = host_ilut["canonical_binary_artifact_manifest"]
    assert binary_manifest["schema_version"] == (
        "canonical-sparse-lu-binary-artifacts.v1"
    )
    assert binary_manifest["storage_profile"] == (
        "canonical_little_endian_sparse_lu_arrays.v1"
    )
    assert binary_manifest["factor_contract_hash"] == manifest["contract_hash"]
    assert binary_manifest["artifact_count"] == 8
    assert binary_manifest["total_byte_length"] == (
        manifest["total_byte_length"]
    )
    assert binary_manifest["total_byte_length"] == 203_136_320
    assert len(binary_manifest["artifacts"]) == 8
    assert host_ilut["apply_backend"] == (
        "canonical_csr_sparse_lu_ordered_python_fsum"
    )
    assert host_ilut["canonical_apply_repeat_byte_exact"] is True
    assert host_ilut["canonical_apply_solution_data_hash"] == (
        host_ilut["canonical_repeat_apply_solution_data_hash"]
    )
    assert host_ilut["canonical_apply_superlu_difference_inf_m"] < 1.0e-9
    assert host_ilut["canonical_factor_contract_pass"] is True
    assert host_ilut["full_scale_ephemeral_binary_roundtrip_pass"] is True
    assert host_ilut["ephemeral_binary_file_count"] == 8
    assert host_ilut["ephemeral_binary_total_byte_length"] == 203_136_320
    assert host_ilut["factor_artifact_bytes_persisted"] is False
    integration = host_ilut["state_tangent_solver_integration"]
    assert integration["profile"] == (
        "matrix_free_cpu_fgmres_canonical_sparse_lu_fixed_right.v1"
    )
    assert integration["preconditioner_profile"] == (
        "canonical_sparse_lu_binary_artifact_fixed_right.v1"
    )
    assert integration["operator_binding_hash"] == payload[
        "operator_binding"
    ]["binding_hash"]
    assert integration["factor_contract_hash"] == manifest["contract_hash"]
    assert integration["binary_artifact_bundle_hash"] == binary_manifest[
        "bundle_hash"
    ]
    assert integration["canonical_factor_source_binding_pass"] is True
    assert integration["binary_artifact_bundle_bound"] is True
    assert integration[
        "operator_callback_outputs_in_contract"
    ] is True
    assert integration[
        "preconditioner_callback_outputs_in_contract"
    ] is True
    assert integration["matrix_free_current_state_operator_action"] is True
    assert integration["materialized_current_tangent"] is False
    assert integration["integration_pass"] is True
    assert integration["production_solver_claim"] is False
    assert integration["rocm_hip_parity_claim"] is False
    assert host_ilut["converged"] is True
    assert host_ilut["terminal_reason"] == "converged_explicit_residual"
    assert host_ilut["iteration_count"] == 6
    assert host_ilut["restart_count"] == 0
    assert host_ilut["operator_action_count"] == 8
    assert host_ilut["preconditioner_application_count"] == 6
    assert host_ilut["explicit_residual_check_count"] == 2
    assert [
        row["iteration"] for row in host_ilut["explicit_observations"]
    ] == [0, 6]
    assert host_ilut["final_explicit_residual_inf_kn"] == pytest.approx(
        4.5821847600491235e-8
    )
    assert host_ilut["final_explicit_residual_inf_kn"] == pytest.approx(
        host_ilut["independent_residual_inf_kn"]
    )
    assert host_ilut["residual_gate_passed"] is True
    assert host_ilut["cpu_diagnostic_effectiveness_pass"] is True
    assert host_ilut[
        "factor_apply_topology_portable_in_principle"
    ] is True
    assert host_ilut[
        "serialized_backend_neutral_factor_contract_implemented"
    ] is True
    assert host_ilut[
        "production_preconditioner_effectiveness_claim"
    ] is False
    assert host_ilut["hip_apply_parity_claim"] is False
    assert host_ilut["performance_claim"] is False

    hip_compile = payload["hip_triangular_apply_compile_evidence"]
    assert hip_compile["schema_version"] == (
        "engine-v2-hip-sparse-lu-apply-target-compile-host-parse-receipt.v1"
    )
    assert hip_compile["contract_scope"] == (
        "target_compile_and_host_fixture_parser_only"
    )
    assert hip_compile["compiler"]["version_first_line"] == (
        "HIP version: 6.0.32831-204d35d16"
    )
    assert [row["architecture"] for row in hip_compile["targets"]] == [
        "gfx1030",
        "gfx1100",
    ]
    assert hip_compile["targets"][0] == {
        "architecture": "gfx1030",
        "binary_byte_length": 57_936,
        "binary_sha256": (
            "sha256:be3b38976dcecec4d4be06fb5a21e60158fbea7b486dc8f3d378"
            "dafe71605751"
        ),
        "host_fixture_parser_execution": True,
        "host_fixture_validation": {
            "actual_hardware_execution": False,
            "contract_pass": True,
            "dimension": 8,
            "fixture_byte_length": 1_232,
            "fixture_hash": (
                "sha256:101104d49783906875453f094cec2a74e2650edfedf773169063ae"
                "80c030c5e1"
            ),
            "hip_runtime_api_call_count": 0,
            "profile": "engine-v2-hip-sparse-lu-host-fixture-parser.v1",
            "runtime_output_hash": (
                "sha256:81f886fd1afdef7a21344207db6b233dea208f70a5418cb32edc4f"
                "28ff85d7bc"
            ),
        },
        "target_compile": True,
    }
    assert hip_compile["targets"][1] == {
        "architecture": "gfx1100",
        "binary_byte_length": 58_192,
        "binary_sha256": (
            "sha256:9c23f463c1a124a64702d2c3b270e872c5e64f9a7e5cdf388190c"
            "104806824aa"
        ),
        "host_fixture_parser_execution": True,
        "host_fixture_validation": hip_compile["targets"][0][
            "host_fixture_validation"
        ],
        "target_compile": True,
    }
    assert hip_compile["dual_target_compile_pass"] is True
    assert hip_compile[
        "dual_target_host_fixture_parser_execution"
    ] is True
    schedule = hip_compile["actual_mgt_dependency_schedule"]
    assert schedule["schedule_profile"] == (
        "csr_triangular_dependency_level_schedule.v1"
    )
    assert schedule["execution_profile"] == (
        "same_stream_level_scheduled_csr_forward_backward.v1"
    )
    assert schedule["factor_contract_hash"] == manifest["contract_hash"]
    assert schedule["dimension"] == 70_560
    assert schedule["lower_nnz"] == manifest["lower_nnz"]
    assert schedule["upper_nnz"] == manifest["upper_nnz"]
    assert schedule["lower_level_count"] == 4_405
    assert schedule["upper_level_count"] == 4_254
    assert schedule["lower_maximum_level_width"] == 14_101
    assert schedule["upper_maximum_level_width"] == 6_637
    assert schedule["lower_level_pointer_data_hash"] == (
        "sha256:b225bd871d391fff34abaad8fc01809814709763ccf2b9533d4b09"
        "e3d74edb82"
    )
    assert schedule["lower_level_rows_data_hash"] == (
        "sha256:6801a6f163f866af69e6d1f6f261738627a115d6c67e6e29423f4"
        "9b052fcf331"
    )
    assert schedule["upper_level_pointer_data_hash"] == (
        "sha256:9bbbc1073585efded4e4773c37f85e0980a7e73cbad961fab746f6"
        "44bf7ca01a"
    )
    assert schedule["upper_level_rows_data_hash"] == (
        "sha256:97ede0291711ff575aef3a70c957ac1d6617d1a9707c1d855a8417"
        "d9e44a8c5b"
    )
    assert schedule["schedule_contract_hash"] == (
        "sha256:25ebdf8fdb6ab2ff8ae2801dad604a51df809353f57d3d0e144a73"
        "9a284af5df"
    )
    assert schedule["right_hand_side_data_hash"] == (
        "sha256:f71a084092ef6d4a89fe6cfbff5d263201d81f88571e784cbca07f"
        "bac93749b2"
    )
    assert schedule["expected_kernel_invocation_count"] == (
        schedule["lower_level_count"]
        + schedule["upper_level_count"]
        + 2
    )
    assert schedule["expected_kernel_invocation_count"] == 8_661
    assert schedule["schedule_array_total_byte_length"] == 1_198_248
    assert schedule["declared_fixture_binary_byte_length"] == (
        48
        + manifest["total_byte_length"]
        + schedule["schedule_array_total_byte_length"]
        + 70_560 * 8
    )
    assert schedule["declared_fixture_binary_byte_length"] == 204_899_096
    assert schedule["schedule_constructed"] is True
    assert schedule["fixture_binary_materialized"] is True
    assert schedule["fixture_binary_ephemeral"] is True
    assert schedule["fixture_binary_sha256"].startswith("sha256:")
    assert schedule["fixture_binary_readback_sha256"] == schedule[
        "fixture_binary_sha256"
    ]
    assert schedule["fixture_binary_roundtrip_pass"] is True
    assert schedule["fixture_binary_persisted"] is False
    assert schedule["device_execution"] is False
    assert hip_compile["actual_hardware_execution"] is False
    assert hip_compile["numerical_parity"] is False
    assert hip_compile["actual_mgt_factor_apply"] is False
    assert hip_compile["production_scale_factor_apply"] is False
    assert hip_compile["production_current_tangent_fgmres"] is False
    assert hip_compile["performance"] is False

    comparison = payload["comparison"]
    assert comparison["same_operator_binding"] is True
    assert comparison["operator_binding_rechecked_before_and_after"] is True
    assert comparison["same_state_and_right_hand_side"] is True
    assert comparison["state_and_right_hand_side_hashes_unchanged"] is True
    assert comparison["same_host_recurrence_profile"] is True
    assert comparison["baseline_gate_passed"] is True
    assert comparison["node_block_jacobi_gate_passed"] is False
    assert comparison[
        "node_block_jacobi_is_insufficient_at_120_iterations"
    ] is True
    assert comparison["host_ilut_gate_passed"] is True
    assert comparison["host_ilut_iterations_over_baseline"] == 2.0
    assert comparison[
        "effective_host_factorized_candidate_identified"
    ] is True
    assert comparison[
        "canonical_factor_contract_and_ordered_cpu_apply_implemented"
    ] is True
    assert comparison[
        "canonical_factor_current_tangent_solver_api_integrated"
    ] is True
    assert comparison[
        "persisted_factor_artifact_and_hip_apply_required"
    ] is True
    assert comparison["stronger_backend_neutral_preconditioner_required"] is True
    assert comparison["contract_pass"] is True

    claims = payload["claims"]
    assert claims["actual_mgt_preconditioner_candidate_compared"] is True
    assert claims["fixed_reference_splu_baseline_gate_passed"] is True
    assert claims["node_block_jacobi_120_iteration_gate_passed"] is False
    assert claims["node_block_jacobi_production_effectiveness"] is False
    assert claims["deterministic_node_block_inverse_construction"] is False
    assert claims["host_ilut_cpu_diagnostic_effectiveness"] is True
    assert claims["deterministic_host_ilut_factor_construction"] is False
    assert claims["canonical_backend_neutral_ilut_factor_contract"] is True
    assert claims["serialized_backend_neutral_ilut_factor_artifact"] is True
    assert claims[
        "full_scale_ephemeral_ilut_factor_binary_roundtrip"
    ] is True
    assert claims["backend_neutral_ilut_triangular_apply"] is True
    assert claims[
        "actual_current_tangent_canonical_factor_cpu_integration"
    ] is True
    assert claims[
        "backend_neutral_current_tangent_operator_contract"
    ] is True
    assert claims[
        "actual_current_tangent_analytic_callback_parity_probes"
    ] is True
    assert claims[
        "operator_callback_formula_and_parent_arrays_in_contract"
    ] is True
    assert claims[
        "actual_mgt_current_tangent_hip_fixture_constructed"
    ] is True
    assert claims[
        "actual_mgt_current_tangent_hip_fixture_ephemeral_roundtrip"
    ] is True
    assert claims[
        "hip_current_tangent_operator_dual_target_compile"
    ] is True
    assert claims[
        "hip_current_tangent_fixture_parser_dual_target_execution"
    ] is True
    assert claims[
        "actual_mgt_current_tangent_host_parser_execution"
    ] is True
    assert claims["actual_mgt_current_tangent_hip_execution"] is True
    assert claims[
        "actual_mgt_current_tangent_cpu_hip_numerical_parity"
    ] is True
    assert claims["actual_mgt_hip_dependency_schedule_constructed"] is True
    assert claims[
        "actual_mgt_hip_fixture_binary_ephemeral_roundtrip"
    ] is True
    assert claims[
        "hip_triangular_fixture_parser_dual_target_execution"
    ] is True
    assert claims["hip_triangular_factor_apply_dual_target_compile"] is True
    assert claims["production_rocm_hip_preconditioner_parity"] is False
    assert claims["performance"] is False
    assert claims["g1_full_building_closure"] is False
    assert "backend_neutral_triangular_factor_apply_not_implemented" not in (
        payload["blockers_remaining"]
    )
    assert "canonical_factor_release_artifact_not_persisted" in (
        payload["blockers_remaining"]
    )
    assert "hip_triangular_factor_apply_not_implemented" not in (
        payload["blockers_remaining"]
    )
    assert "hip_triangular_factor_apply_not_executed" in (
        payload["blockers_remaining"]
    )
    assert (
        "actual_mgt_current_tangent_fixture_host_parser_not_executed"
        not in payload["blockers_remaining"]
    )
    assert "current_tangent_operator_hip_execution_not_performed" not in (
        payload["blockers_remaining"]
    )
    assert (
        "current_tangent_operator_cpu_hip_numerical_parity_not_verified"
        not in payload["blockers_remaining"]
    )
    assert payload["artifacts"]["factor_contract_module"] == (
        "src/structural_analysis/solvers/nonlinear/canonical_sparse_lu.py"
    )
    assert payload["artifacts"]["factor_binary_artifact_schema"] == (
        "src/structural_analysis/schemas/"
        "canonical_sparse_lu_binary_artifacts_v1.schema.json"
    )
    assert payload["artifacts"]["hip_triangular_apply_source"] == (
        "implementation/phase1/hip_kernels/engine_v2_sparse_lu_apply.hip.cpp"
    )
    assert payload["artifacts"][
        "hip_triangular_apply_compile_receipt"
    ] == (
        "implementation/phase1/release_evidence/productization/"
        "engine_v2_hip_sparse_lu_apply_compile_receipt.json"
    )
    assert payload["artifacts"][
        "hip_current_tangent_operator_module"
    ] == (
        "src/structural_analysis/engine_v2_backends/"
        "hip_current_tangent_operator.py"
    )
    assert payload["artifacts"][
        "hip_current_tangent_operator_source"
    ] == (
        "implementation/phase1/hip_kernels/"
        "engine_v2_current_tangent_operator.hip.cpp"
    )
    assert payload["artifacts"][
        "hip_current_tangent_operator_compile_receipt"
    ] == (
        "implementation/phase1/release_evidence/productization/"
        "engine_v2_hip_current_tangent_operator_compile_receipt.json"
    )
    assert payload["artifacts"][
        "hip_current_tangent_actual_mgt_host_parser_receipt"
    ] == (
        "implementation/phase1/release_evidence/productization/"
        "g1_mgt_hip_current_tangent_host_parser_receipt.json"
    )
    assert payload["artifacts"][
        "hip_current_tangent_actual_mgt_host_parser_builder"
    ] == (
        "scripts/"
        "build_g1_mgt_hip_current_tangent_host_parser_receipt.py"
    )
    assert payload["artifacts"][
        "hip_current_tangent_actual_mgt_host_parser_schema"
    ] == (
        "src/structural_analysis/schemas/"
        "g1_mgt_hip_current_tangent_host_parser_receipt_v1.schema.json"
    )
    assert payload["artifacts"][
        "hip_current_tangent_actual_mgt_hardware_receipt"
    ] == (
        "implementation/phase1/release_evidence/productization/"
        "g1_mgt_hip_current_tangent_hardware_parity_receipt.json"
    )
    assert payload["artifacts"][
        "hip_current_tangent_actual_mgt_hardware_action"
    ] == (
        "implementation/phase1/release_evidence/productization/"
        "g1_mgt_hip_current_tangent_action.f64le"
    )
    assert payload["artifacts"][
        "hip_current_tangent_actual_mgt_hardware_runner"
    ] == "scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py"
    assert payload["artifacts"][
        "hip_current_tangent_actual_mgt_hardware_schema"
    ] == (
        "src/structural_analysis/schemas/"
        "g1_mgt_hip_current_tangent_hardware_parity_receipt_v1.schema.json"
    )

    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_committed_input_checksums_match_files() -> None:
    payload = _committed_receipt()

    for relative_path, expected in payload["input_checksums"].items():
        assert module.file_sha256(ROOT / relative_path) == expected


def test_committed_receipt_is_reproducible() -> None:
    passed, reason = module.check_receipt(repo_root=ROOT)

    assert passed is True, reason
    assert reason == "g1_mgt_preconditioner_candidate_audit_consistent"
