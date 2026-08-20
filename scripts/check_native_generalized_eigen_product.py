#!/usr/bin/env python3
"""Verify bounded generalized-eigen C4/C5 product evidence without over-promoting C2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/crates/structural-contracts/src/spectral_product.rs": (
        "structural-dense-spectral-request.v1",
        "structural-dense-spectral-result-ir.v1",
        "structural-dense-spectral-report-ir.v1",
        "rigid_mode_count",
        "finite_positive_eigenvalue_count",
        "spectral_result_model_hash_mismatch",
        "spectral_result_execution_hash_mismatch",
        "spectral_result_modal_derived_value_invalid",
        "spectral_result_buckling_derived_value_invalid",
    ),
    "native/crates/structural-contracts/tests/spectral_product_wire.rs": (
        "result_and_report_round_trip_as_exact_self_hashed_wire_documents",
        "identity_derived_values_variants_and_self_hashes_fail_closed",
    ),
    "native/crates/structural-runtime/src/spectral_checkpoint.rs": (
        'b"SAEIGC01"',
        'b"structural-dense-spectral-ready-state.v1\\0"',
        'b"structural-dense-spectral-checkpoint.v1\\0"',
        "validated_ready_for_atomic_native_solve",
        "CHECKPOINT_MISMATCH",
        "dense_spectral_execution_hash_v1",
    ),
    "native/crates/structural-runtime/src/lib.rs": (
        "checkpoint_dense_spectral",
        "restore_dense_spectral",
        "execute_dense_spectral_product",
        "Api::load_generalized_eigen",
        "build_dense_spectral_result_ir_v1",
    ),
    "native/crates/structural-runtime/tests/spectral_checkpoint_product.rs": (
        "phase_checkpoint_round_trip_binds_all_identities_and_exact_request",
        "every_artifact_region_and_request_drift_fail_closed",
        "direct_and_checkpoint_resume_results_are_bitwise_identical",
        "wrong taxonomy at byte",
    ),
    "native/crates/structural-report/src/lib.rs": (
        "build_dense_spectral_report_v1",
        "bounded dense spectral candidate",
    ),
    "native/crates/structural-cli/src/spectral_product.rs": (
        "execute_dense_spectral_analysis",
        "publish_dense_spectral_analysis",
        "checkpoint.eigcp",
        "receipt_hash",
    ),
    "native/crates/structural-cli/src/main.rs": (
        '"eigen-run"',
        '"eigen-resume"',
        '"--output-dir"',
    ),
    "native/crates/structural-cli/tests/dense_spectral_product_cli.rs": (
        "python_node_free_modal_and_buckling_direct_resume_are_byte_identical",
        "command.env_clear()",
        "assert_same_artifacts",
        "tamper_request_drift_and_existing_destination_publish_nothing",
    ),
    "native/crates/structural-contracts/src/model_modal_product.rs": (
        "structural-model-ir-modal-analysis-request.v1",
        "assembly_load_pattern_id",
        "MODEL_IR_MODAL_MAXIMUM_REQUEST_BYTES",
        "deny_unknown_fields",
    ),
    "native/crates/structural-runtime/src/model_modal_product.rs": (
        "prepare_model_ir_modal_product",
        "MAXIMUM_MODAL_ORDER",
        "csr_to_dense",
        "operator is not exactly symmetric",
        "load_vector_consumed_by_modal",
    ),
    "native/crates/structural-runtime/src/model_modal_checkpoint.rs": (
        'b"SAMMCP01"',
        "structural-model-ir-modal-checkpoint.v1",
        "ModelIrModalCheckpointBindingsV1",
        "verify_bindings",
        "inner_checkpoint_hash",
    ),
    "native/crates/structural-runtime/tests/model_ir_modal_checkpoint.rs": (
        "modal_checkpoint_round_trip_preserves_every_outer_and_inner_binding",
        "every_modal_checkpoint_byte_and_each_outer_binding_fail_closed",
        "wrong taxonomy at byte",
        "truncation must fail",
        "trailing bytes must fail",
    ),
    "native/crates/structural-runtime/tests/model_ir_modal_product.rs": (
        "typed_model_ir_assembly_drives_existing_native_modal_product",
        "identity_drift_and_excess_mode_request_fail_closed",
        "execute_dense_spectral_product",
        "one_element_cantilever_bending_eigenvalue",
        "5.0e-15",
    ),
    "native/crates/structural-cli/src/model_modal_product.rs": (
        "execute_model_ir_modal_analysis",
        "execute_model_ir_modal_analysis_with_checkpoint",
        "publish_model_ir_modal_analysis",
        "validate_model_ir_modal_analysis_compatibility",
        "structural-model-ir-modal-run-receipt.v1",
        "generated-dense-request.json",
        "checkpoint.mmcp",
    ),
    "native/crates/structural-cli/tests/model_ir_modal_product_cli.rs": (
        "python_node_free_modelir_modal_direct_resume_are_byte_identical_and_bound",
        "modelir_modal_resume_rejects_tamper_and_outer_binding_drift_without_publication",
        "env_clear()",
        "expected_files",
        "verify_self_hash",
    ),
    "native/crates/structural-workbench/src/analysis_request.rs": (
        "publish_model_modal_analysis_request",
        "create_model_modal_analysis_request",
        "structural-native-model-modal-request-create-receipt.v1",
        "cpp_active_k_m_assembly_preflight_verified",
        "execution_started",
    ),
    "native/crates/structural-workbench/src/main.rs": (
        'Some("model-create-modal-analysis-request")',
        "--assembly-load-pattern",
        "--positive-semidefinite-relative-tolerance",
        "--eigensolver-relative-tolerance",
    ),
    "native/crates/structural-workbench/tests/model_ir_modal_request_create.rs": (
        "workbench_authors_preflighted_request_that_executes_without_rebinding",
        "clean_environment_cli_publishes_byte_identical_request_and_receipt",
        "load_vector_consumed_by_modal",
        "env_clear()",
    ),
    "native/crates/structural-workbench/src/modal_result_view.rs": (
        "structural-native-workbench-model-ir-modal-result-view.v1",
        "render_model_ir_modal_result_view_directory",
        "EXPECTED_FILES",
        "ModelIrModalCheckpointV1::from_bytes",
        "parse_dense_spectral_result_ir_v1",
        "View hash",
    ),
    "native/crates/structural-workbench/tests/model_ir_modal_result_view.rs": (
        "clean_environment_modal_result_view_is_localized_deterministic_and_read_only",
        "modal_result_view_rejects_inventory_hash_and_window_drift",
        "env_clear()",
        "verify_view_hash",
    ),
    "docs/native/generalized-eigen-product-e2e-v1.md": (
        "C4",
        "C5",
        "SAEIGC01",
        "phase boundary",
        "Python/Node",
        "protected-runner C2",
        "C6",
    ),
    "docs/native/model-ir-modal-product-e2e-v1.md": (
        "C5",
        "ABI v1.14",
        "ABI v1.9",
        "128 active DOFs",
        "Python/Node",
        "linear-buckling",
        "protected-runner HIP C2",
        "C6",
        "model-create-modal-analysis-request",
        "execution_started=false",
        "model-modal-resume",
        "SAMMCP01",
        "modal-result-view",
    ),
}


def _check_capability(
    payload: dict[str, object],
    capability: str,
    gate: str,
    owner: str,
    claim_tokens: tuple[str, ...],
    blockers: list[str],
) -> dict[str, object]:
    try:
        row = payload["capabilities"][capability]  # type: ignore[index]
    except (KeyError, TypeError):
        blockers.append(f"{capability}_capability_manifest_invalid")
        return {}
    if not isinstance(row, dict):
        blockers.append(f"{capability}_capability_manifest_invalid")
        return {}
    if row.get("status") != "implemented":
        blockers.append(f"{capability}_capability_not_implemented")
    if row.get("cutover_gate") != gate:
        blockers.append(f"{capability}_capability_gate_not_{gate.lower()}")
    if row.get("owner") != owner:
        blockers.append(f"{capability}_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in claim_tokens:
        if token not in claim:
            blockers.append(f"{capability}_scope_token_missing:{token}")
    return row


def check_generalized_eigen_product(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(f"generalized_eigen_product_manifest_invalid:{exc}")
        payload = {}

    checkpoint = _check_capability(
        payload,
        "generalized_eigen_checkpoint",
        "C4",
        "structural-runtime",
        (
            "bounded dense CPU",
            "phase-boundary checkpoint",
            "model, ready-state, execution",
            "mid-Jacobi",
            "HIP C2",
            "C6",
        ),
        blockers,
    )
    product = _check_capability(
        payload,
        "generalized_eigen_product_e2e",
        "C5",
        "structural-cli",
        (
            "bounded dense CPU",
            "ResultIR, ReportIR",
            "eigen-run/eigen-resume",
            "no Python or Node",
            "HIP C2",
            "C6",
        ),
        blockers,
    )
    modelir_modal_product = _check_capability(
        payload,
        "modelir_modal_product_e2e",
        "C5",
        "structural-cli",
        (
            "typed-ModelIR frame3d/truss3d CPU modal",
            "128 DOFs",
            "ABI v1.14",
            "ABI v1.9",
            "byte-identical 11-artifact",
            "model-bound checkpoint",
            "independent 2x2 closed-form",
            "fallback 0",
            "linear buckling",
            "HIP C2",
            "C6",
        ),
        blockers,
    )
    modelir_modal_authoring = _check_capability(
        payload,
        "modelir_modal_request_authoring",
        "C5",
        "structural-workbench",
        (
            "model-create-modal-analysis-request",
            "ABI v1.14",
            "128-DOF",
            "execution_started false",
            "ABI v1.9",
            "Python/Node-free",
            "installed static/shared distribution v90",
            "HIP C2",
            "C6",
        ),
        blockers,
    )
    modelir_modal_result_view = _check_capability(
        payload,
        "modelir_modal_result_view",
        "C5",
        "structural-workbench",
        (
            "modal-result-view",
            "exact eleven-artifact",
            "en-US or ko-KR",
            "source directory remains unchanged",
            "installed distribution v90",
            "HIP C2",
            "C6",
        ),
        blockers,
    )

    for relative, tokens in REQUIRED_TOKENS.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"generalized_eigen_product_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(
                    "generalized_eigen_product_evidence_token_missing:"
                    f"{relative}:{token}"
                )

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-generalized-eigen-product-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "checkpoint_gate": checkpoint.get("cutover_gate"),
        "product_gate": product.get("cutover_gate"),
        "modelir_modal_product_gate": modelir_modal_product.get("cutover_gate"),
        "modelir_modal_authoring_gate": modelir_modal_authoring.get("cutover_gate"),
        "modelir_modal_result_view_gate": modelir_modal_result_view.get("cutover_gate"),
        "sequential_numerical_gate": "C1",
        "blockers": blockers,
        "claim_boundary": (
            "C4/C5 are bounded dense CPU implementation capabilities. The generalized-"
            "eigen numerical family remains sequentially at C1 until an approved protected-"
            "runner HIP C2 receipt exists; the bounded ModelIR modal C5 path cannot promote "
            "general sparse or buckling authority and cannot promote C2 or C6."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_generalized_eigen_product(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native generalized-eigen product contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
